// 좌측 탐색기 — 실제 파일시스템을 서버 API로 읽는다. 펼친 폴더만 불러온다.
import { api } from "./api.js";
import { toast } from "./menu.js";

export function createExplorer(treeEl, hooks) {
  const cache = new Map();        // path -> entries[]
  const open = new Set();         // 펼쳐진 폴더
  let root = null, sel = null;

  async function load(dir, force) {
    if (!force && cache.has(dir)) return cache.get(dir);
    try {
      const r = await api.list(dir);
      cache.set(dir, r.entries);
      return r.entries;
    } catch (e) {
      toast(`${dir} — ${e.message}`);
      cache.set(dir, []);
      return [];
    }
  }

  function join(dir, name) {
    const sep = dir.includes("\\") || /^[A-Za-z]:$/.test(dir) ? "\\" : "/";
    return dir.endsWith(sep) ? dir + name : dir + sep + name;
  }
  const leaf = p => p.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || p;

  function rowHTML(entry, path, depth) {
    const cls = entry.dir ? "dir" : "file";
    const tw = entry.dir ? (open.has(path) ? "&#9660;" : "&#9654;") : "";
    const ic = entry.dir ? (open.has(path) ? "&#128194;" : "&#128193;") : "&#128196;";
    return `<div class="row ${cls} ${sel === path ? "sel" : ""} ${entry.hidden ? "hidden" : ""}"
      data-p="${escAttr(path)}" data-dir="${entry.dir ? 1 : 0}" style="padding-left:${6 + depth * 13}px">
      <span class="tw">${tw}</span><span class="ic">${ic}</span><span class="nm">${escHTML(entry.name)}</span></div>`;
  }

  async function render() {
    if (!root) return;
    const parts = [`<div class="row dir ${sel === root ? "sel" : ""}" data-p="${escAttr(root)}" data-dir="1" style="padding-left:6px">
        <span class="tw">&#9660;</span><span class="ic">&#128194;</span><span class="nm">${escHTML(leaf(root))}</span></div>`];
    await walk(root, 1);
    treeEl.innerHTML = parts.join("");

    async function walk(dir, depth) {
      const entries = await load(dir);
      for (const e of entries) {
        const p = join(dir, e.name);
        parts.push(rowHTML(e, p, depth));
        if (e.dir && open.has(p)) await walk(p, depth + 1);
      }
    }
  }

  treeEl.addEventListener("click", async ev => {
    const row = ev.target.closest(".row"); if (!row) return;
    const p = row.dataset.p, isDir = row.dataset.dir === "1";
    sel = p;
    if (isDir) { open.has(p) ? open.delete(p) : (open.add(p), await load(p)); }
    await render();
    hooks.onSelect?.(p, isDir);
  });
  treeEl.addEventListener("dblclick", ev => {
    const row = ev.target.closest(".row"); if (!row || row.dataset.dir === "1") return;
    api.open(row.dataset.p).catch(e => toast(e.message));
  });
  treeEl.addEventListener("contextmenu", async ev => {
    const row = ev.target.closest(".row"); if (!row) return;
    ev.preventDefault();
    sel = row.dataset.p; await render();
    hooks.onContext?.(row.dataset.p, leaf(row.dataset.p), row.dataset.dir === "1", ev.clientX, ev.clientY, ev);
  });

  // 이름 바꾸기는 그 자리에서
  function renameAt(path) {
    const row = treeEl.querySelector(`.row[data-p="${cssEsc(path)}"]`); if (!row) return;
    const nm = row.querySelector(".nm"), old = nm.textContent;
    nm.innerHTML = `<input value="${escAttr(old)}">`;
    const inp = nm.querySelector("input"); inp.focus(); inp.select();
    const done = async ok => {
      const v = inp.value.trim();
      if (ok && v && v !== old) {
        try { await api.rename(path, v); } catch (e) { toast(e.message); }
      }
      await refresh(parentOf(path));
    };
    inp.addEventListener("keydown", e => { e.stopPropagation(); if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); });
    inp.addEventListener("blur", () => done(true));
  }

  const parentOf = p => {
    if (/^[A-Za-z]:[\\/]?$/.test(p) || p === "/" || /^\\\\[^\\/]+[\\/]?[^\\/]*[\\/]?$/.test(p)) return p;  // 드라이브·UNC 루트
    const up = p.replace(/[\\/]+$/, "").replace(/[\\/][^\\/]+$/, "");
    if (!up) return "/";
    return /^[A-Za-z]:$/.test(up) ? up + "\\" : up;      // "C:" 가 아니라 "C:\"
  };

  async function refresh(dir) { await load(dir || root, true); await render(); }
  async function setRoot(p) { root = p; open.clear(); open.add(p); cache.clear(); sel = p; await render(); }

  return {
    setRoot, refresh, render, renameAt,
    get root() { return root; },
    get selected() { return sel || root; },
    parentOf, join, leaf
  };
}

const escHTML = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const escAttr = s => escHTML(s).replace(/"/g, "&quot;");
const cssEsc  = s => (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/["\\]/g, "\\$&");
