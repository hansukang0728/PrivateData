// 파일 작업 — 탐색기가 쓰는 것들. 접근 범위는 config.roots 가 정한다(기본: 제한 없음).
import fs from "node:fs/promises";
import fss from "node:fs";
import path from "node:path";
import os from "node:os";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const pexec = promisify(execFile);
const isWin = process.platform === "win32";

export function normalize(p) {
  if (!p) throw new Error("경로가 없습니다");
  const abs = path.resolve(p);
  return abs;
}

// roots 가 비어 있으면 제한 없음. 좁히고 싶으면 config.json 의 roots 에 폴더를 넣는다.
export function guard(p, roots) {
  const abs = normalize(p);
  if (!roots || !roots.length) return abs;
  const ok = roots.some(r => {
    const root = path.resolve(r);
    const rel = path.relative(root, abs);
    return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
  });
  if (!ok) { const e = new Error("허용되지 않은 경로입니다: " + abs); e.code = "OUT_OF_ROOT"; throw e; }
  return abs;
}

export async function drives() {
  if (!isWin) return [{ name: "/", path: "/" }, { name: "~", path: os.homedir() }];
  const out = [];
  for (let c = 65; c <= 90; c++) {
    const letter = String.fromCharCode(c) + ":\\";
    try { if (fss.existsSync(letter)) out.push({ name: String.fromCharCode(c) + ":", path: letter }); } catch {}
  }
  return out;
}

export async function list(dir) {
  const abs = normalize(dir);
  const ents = await fs.readdir(abs, { withFileTypes: true });
  const rows = [];
  for (const e of ents) {
    const full = path.join(abs, e.name);
    let size = 0, mtime = null, hidden = false;
    try {
      const st = await fs.stat(full);
      size = st.size; mtime = st.mtimeMs;
    } catch { continue; }                      // 권한 없는 항목은 조용히 건너뛴다
    if (e.name.startsWith(".")) hidden = true;
    rows.push({ name: e.name, dir: e.isDirectory(), size, mtime, hidden });
  }
  rows.sort((a, b) => (a.dir === b.dir ? a.name.localeCompare(b.name, "ko") : a.dir ? -1 : 1));
  return { path: abs, parent: path.dirname(abs) === abs ? null : path.dirname(abs), entries: rows };
}

export async function mkdir(dir, name) {
  const target = path.join(normalize(dir), name || "새 폴더");
  await fs.mkdir(target, { recursive: false });
  return target;
}

export async function newFile(dir, name) {
  const target = path.join(normalize(dir), name || "새 파일.txt");
  const fh = await fs.open(target, "wx"); await fh.close();
  return target;
}

export async function rename(from, to) {
  const src = normalize(from);
  const dst = path.join(path.dirname(src), to);
  await fs.rename(src, dst);
  return dst;
}

// 기본은 휴지통. permanent 를 줘야 진짜 지운다.
export async function remove(target, permanent) {
  const abs = normalize(target);
  if (permanent || !isWin) {
    await fs.rm(abs, { recursive: true, force: true });
    return { path: abs, permanent: true };
  }
  const ps = [
    "Add-Type -AssemblyName Microsoft.VisualBasic;",
    `$p = '${abs.replace(/'/g, "''")}';`,
    "if (Test-Path -LiteralPath $p -PathType Container) {",
    "  [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p,'OnlyErrorDialogs','SendToRecycleBin')",
    "} else {",
    "  [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p,'OnlyErrorDialogs','SendToRecycleBin')",
    "}"
  ].join(" ");
  await pexec("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", ps], { windowsHide: true });
  return { path: abs, permanent: false };
}

function uniquePath(dst) {
  if (!fss.existsSync(dst)) return dst;
  const dir = path.dirname(dst), ext = path.extname(dst), base = path.basename(dst, ext);
  for (let i = 2; i < 1000; i++) {
    const cand = path.join(dir, `${base} (${i})${ext}`);
    if (!fss.existsSync(cand)) return cand;
  }
  return path.join(dir, `${base} (${Date.now()})${ext}`);
}

export async function transfer(sources, destDir, move) {
  const dir = normalize(destDir);
  const done = [];
  for (const src of sources) {
    const abs = normalize(src);
    const dst = uniquePath(path.join(dir, path.basename(abs)));
    if (move) await fs.rename(abs, dst);
    else await fs.cp(abs, dst, { recursive: true });
    done.push(dst);
  }
  return done;
}
