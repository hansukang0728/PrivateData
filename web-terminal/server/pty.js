// PTY 세션 관리 — 셸을 띄우고, 출력을 나눠주고, "지금 바쁜가"와 "지금 어디인가"를 추적한다.
import os from "node:os";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
let pty = null;
try { pty = require("node-pty"); } catch (e) { console.error("[PoshDeck] node-pty 로드 실패:", e.message); }

const OSC_DONE = /\u001b\]633;D\u0007/;                 // 프롬프트가 그려졌다 = 명령이 끝났다
const OSC_CWD  = /\u001b\]633;P;Cwd=(.*?)\u0007/g;      // 프롬프트가 알려주는 현재 폴더
const BUF_MAX  = 256 * 1024;                            // 재접속용 출력 보관량
const IDLE_MS  = 600;                                   // 표시를 못 쓰는 셸(cmd/wsl)용 대략 판정

export const sessions = new Map();

export function dataDir() {
  const base = process.platform === "win32"
    ? (process.env.LOCALAPPDATA || os.homedir())
    : path.join(os.homedir(), ".local", "share");
  const dir = path.join(base, "poshdeck");
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

// PowerShell 이 프롬프트마다 상태를 알려주도록 초기화 스크립트를 깔아둔다.
// -Command 로 넘기면 따옴표 지옥이라 파일로 두고 -File 로 읽힌다.
function psInitFile() {
  const p = path.join(dataDir(), "psinit.ps1");
  const body = [
    "# PoshDeck 초기화 — 지우면 다시 생성됩니다",
    "try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}",
    "try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}",
    "function global:prompt {",
    "  $esc = [char]27; $bel = [char]7",
    "  $loc = $executionContext.SessionState.Path.CurrentLocation",
    "  $mark = \"$esc]633;D$bel$esc]633;P;Cwd=$($loc.Path)$bel\"",
    "  $mark + 'PS ' + $loc.Path + ('>' * ($nestedPromptLevel + 1)) + ' '",
    "}"
  ].join("\r\n");
  try { fs.writeFileSync(p, body, "utf8"); } catch {}
  return p;
}

export function resolveShell(kind) {
  if (process.platform !== "win32") {
    // 개발 환경(리눅스/맥)에서는 기본 셸로 대신 돈다. 상태 표시는 시간 기반으로 떨어진다.
    return { file: process.env.SHELL || "/bin/bash", args: ["-i"], marker: false, label: "bash" };
  }
  const sysRoot = process.env.SystemRoot || "C:\\Windows";
  const init = psInitFile();
  switch (kind) {
    case "powershell":
      return { file: path.join(sysRoot, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
               args: ["-NoLogo", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", init], marker: true, label: "Windows PowerShell" };
    case "cmd":
      return { file: process.env.ComSpec || path.join(sysRoot, "System32", "cmd.exe"),
               args: ["/K", "chcp 65001 >nul"], marker: false, label: "cmd" };
    case "wsl":
      return { file: "wsl.exe", args: [], marker: false, label: "WSL" };
    case "pwsh":
    default: {
      const candidates = [
        path.join(process.env.ProgramFiles || "C:\\Program Files", "PowerShell", "7", "pwsh.exe"),
        path.join(process.env.LOCALAPPDATA || "", "Microsoft", "WindowsApps", "pwsh.exe")
      ];
      const file = candidates.find(p => { try { return fs.existsSync(p); } catch { return false; } }) || "pwsh.exe";
      return { file, args: ["-NoLogo", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", init], marker: true, label: "PowerShell 7" };
    }
  }
}

function emit(s, msg) { for (const fn of s.listeners) { try { fn(msg); } catch {} } }

function remember(s, chunk) {
  s.buf.push(chunk);
  s.bytes += chunk.length;
  while (s.bytes > BUF_MAX && s.buf.length > 1) s.bytes -= s.buf.shift().length;
}

function setBusy(s, busy) {
  if (s.busy === busy) return;
  s.busy = busy;
  emit(s, { t: "state", id: s.id, busy, cwd: s.cwd });
}

export function spawn({ id, cwd, shell = "pwsh", cols = 80, rows = 24 }) {
  if (!pty) throw new Error("node-pty 를 불러오지 못했습니다. npm install 을 다시 실행해 주세요.");
  if (sessions.has(id)) return sessions.get(id);

  const sh = resolveShell(shell);
  let startDir = cwd;
  try { if (!startDir || !fs.statSync(startDir).isDirectory()) startDir = os.homedir(); }
  catch { startDir = os.homedir(); }

  const p = pty.spawn(sh.file, sh.args, {
    name: "xterm-256color",
    cols, rows, cwd: startDir,
    env: { ...process.env, TERM: "xterm-256color", POSHDECK: "1" },
    useConpty: process.platform === "win32" ? undefined : false
  });

  const s = {
    id, pty: p, shell, shellLabel: sh.label, marker: sh.marker,
    cwd: startDir, buf: [], bytes: 0, busy: false, exited: false,
    tail: "", idleTimer: null, listeners: new Set()
  };
  sessions.set(id, s);

  p.onData(chunk => {
    remember(s, chunk);
    // 시퀀스가 청크 경계에서 잘릴 수 있어 꼬리를 물려가며 본다
    const hay = s.tail + chunk;
    let m, last = null;
    OSC_CWD.lastIndex = 0;
    while ((m = OSC_CWD.exec(hay)) !== null) last = m[1];
    if (last && last !== s.cwd) { s.cwd = last; emit(s, { t: "state", id: s.id, busy: s.busy, cwd: s.cwd }); }
    if (s.marker && OSC_DONE.test(hay)) setBusy(s, false);
    s.tail = hay.slice(-512);

    if (!s.marker) {                                  // 표시가 없는 셸은 잠잠해지면 끝난 걸로 본다
      clearTimeout(s.idleTimer);
      s.idleTimer = setTimeout(() => setBusy(s, false), IDLE_MS);
    }
    emit(s, { t: "out", id: s.id, d: chunk });
  });

  p.onExit(({ exitCode }) => {
    s.exited = true;
    clearTimeout(s.idleTimer);
    emit(s, { t: "exit", id: s.id, code: exitCode });
    sessions.delete(s.id);
  });

  return s;
}

export function write(id, data) {
  const s = sessions.get(id); if (!s || s.exited) return;
  if (data.includes("\r")) setBusy(s, true);          // 엔터를 쳤다 = 뭔가 돌기 시작했다
  s.pty.write(data);
}

export function resize(id, cols, rows) {
  const s = sessions.get(id); if (!s || s.exited) return;
  try { s.pty.resize(Math.max(2, cols | 0), Math.max(1, rows | 0)); } catch {}
}

export function kill(id) {
  const s = sessions.get(id); if (!s) return;
  try { s.pty.kill(); } catch {}
  sessions.delete(id);
}

export function attach(id, fn) {
  const s = sessions.get(id); if (!s) return null;
  s.listeners.add(fn);
  return { buffer: s.buf.join(""), cwd: s.cwd, busy: s.busy, shellLabel: s.shellLabel };
}

export function detach(id, fn) {
  const s = sessions.get(id); if (s) s.listeners.delete(fn);
}

export function killAll() { for (const id of [...sessions.keys()]) kill(id); }
