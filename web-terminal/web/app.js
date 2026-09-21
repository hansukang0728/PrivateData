// PoshDeck — 그룹(부모 1 + 자식 N) 구조로 터미널을 다룬다. 규칙은 SPEC-groups.md.
import { THEMES, applyTheme, xtermTheme } from "./themes.js";
import * as conn from "./conn.js";
import { showMenu, closeMenu, toast } from "./menu.js";
import { api } from "./api.js";
import { createPane } from "./term.js";
import { createExplorer } from "./explorer.js";

const $ = s => document.querySelector(s);
const app = $("#app");

const KC = ["cyan", "magenta", "yellow", "green"];      // 자식 구분색
const FS_MIN = 9, FS_MAX = 22, FS_DEF = 13;
const SHELLS = [["PowerShell 7", "pwsh"], ["Windows PowerShell 5.1", "powershell"], ["명령 프롬프트", "cmd"], ["Ubuntu (WSL)", "wsl"]];

const S = {
  layout: "ide", theme: "tokyonight", maxVisible: 3, fontSize: FS_DEF, expHidden: false,
  groups: [], terms: {}, activeGroup: null, focusedTerm: null,
  home: "", platform: "win32", defaultShell: "pwsh"
};
const panes = new Map();                                 // termId -> createPane(...)
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : "t" + Math.random().toString(16).slice(2) + Date.now());

const sep = () => (S.platform === "win32" ? "\\" : "/");
const leaf = p => String(p).replace(/[\\/]+$/, "").split(/[\\/]/).pop() || p;
const join = (dir, name) => (dir.endsWith(sep()) ? dir + name : dir + sep() + name);
const shortPath = p => { const a = String(p).split(/[\\/]/); return a.length <= 3 ? p : "…" + sep() + a.slice(-2).join(sep()); };
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const groupOf = id => S.groups.find(g => g.id === S.terms[id]?.groupId);
const groupTerms = g => [g.parentId, ...g.children];
const activeGroup = () => S.groups.find(g => g.id === S.activeGroup) || S.groups[0];

// ─────────────────────────────────────────────── 터미널·그룹
function mkTerm(o) {
  const t = { id: o.id || uid(), groupId: o.groupId, role: o.role, name: o.name || leaf(o.cwd),
              cwd: o.cwd, birthCwd: o.birthCwd || o.cwd, shell: o.shell || S.defaultShell,
              hue: o.hue, busy: false, dead: false, fs: o.fs || null, lastUse: ++mkTerm.clock };
  S.terms[t.id] = t;
  return t;
}
mkTerm.clock = 0;

function paneOf(t) {
  let p = panes.get(t.id);
  if (p) return p;
  p = createPane(t, {
    fontSize: () => S.fontSize, theme: () => xtermTheme(THEMES[S.theme]),
    isWindows: () => S.platform === "win32", isShortcut,
    onFocus: id => focus(id),
    onState: id => { updateHead(id); renderTabs(); updateStatus(); }
  });
  panes.set(t.id, p);
  return p;
}

function newGroup(cwd, shell, opts = {}) {
  const g = { id: opts.id || "g" + uid(), parentId: null, children: [], visible: [], ratio: opts.ratio || 0.6 };
  const p = mkTerm({ id: opts.parentId, groupId: g.id, role: "parent", cwd, shell, name: opts.name });
  g.parentId = p.id;
  S.groups.push(g);
  S.activeGroup = g.id; S.focusedTerm = p.id;
  return g;
}

function addChild(g, cwd, shell) {
  const t = mkTerm({ groupId: g.id, role: "child", cwd, shell: shell || S.terms[g.parentId].shell });
  g.children.push(t.id);
  g.visible.push(t.id);
  t.hue = KC[(g.children.length - 1) % KC.length];
  enforceVisible(g);
  S.activeGroup = g.id; S.focusedTerm = t.id;
  render(); save();
  return t;
}

// 화면 자식 수 한도 — 가장 오래 안 쓴 자식을 접는다. 실행 중인 자식은 끝까지 보호.
function enforceVisible(g, silent) {
  while (g.visible.length > S.maxVisible) {
    const cands = g.visible.slice(0, -1);
    cands.sort((a, b) => {
      const A = S.terms[a], B = S.terms[b];
      if (A.busy !== B.busy) return A.busy ? 1 : -1;
      return A.lastUse - B.lastUse;
    });
    const ev = cands[0] ?? g.visible[0];
    g.visible = g.visible.filter(x => x !== ev);
    if (!silent) toast(`${S.terms[ev].name} — 자리를 양보해 접혔습니다 (세션은 그대로 살아 있습니다)`);
  }
}

function unfold(id) {
  const g = groupOf(id);
  if (!g.visible.includes(id)) g.visible.push(id);
  enforceVisible(g);
  S.activeGroup = g.id;
  focus(id);
}

function focus(id) {
  if (!S.terms[id]) return;
  S.focusedTerm = id;
  S.terms[id].lastUse = ++mkTerm.clock;
  S.activeGroup = S.terms[id].groupId;
  document.querySelectorAll(".pane").forEach(p => p.classList.toggle("focus", p.dataset.id === id));
  panes.get(id)?.term.focus();
  renderTabs(); updateStatus();
}

async function closeTerm(id) {
  const g = groupOf(id), t = S.terms[id];
  if (!g || !t) return;
  if (t.role === "parent") {
    const busy = groupTerms(g).filter(x => S.terms[x]?.busy).map(x => S.terms[x].name);
    if (g.children.length || busy.length) {
      const lines = [`이 그룹을 닫으면 자식 ${g.children.length}개도 함께 닫힙니다.`];
      if (busy.length) lines.push("", "실행 중: " + busy.join(", "));
      lines.push("", "닫을까요?");
      if (!confirm(lines.join("\n"))) return;
    }
    if (S.groups.length === 1) { toast("마지막 그룹은 닫을 수 없습니다"); return; }
    groupTerms(g).forEach(dropTerm);
    S.groups = S.groups.filter(x => x !== g);
    const ng = S.groups[0];
    S.activeGroup = ng.id; S.focusedTerm = ng.parentId;
  } else {
    if (t.busy && !confirm(`${t.name} 에서 뭔가 실행 중입니다. 닫을까요?`)) return;
    g.children = g.children.filter(x => x !== id);
    g.visible = g.visible.filter(x => x !== id);
    dropTerm(id);
    const folded = g.children.filter(x => !g.visible.includes(x));    // 접혀 있던 자식이 올라온다
    if (folded.length) g.visible.push(folded.sort((a, b) => S.terms[b].lastUse - S.terms[a].lastUse)[0]);
    S.focusedTerm = g.parentId;
  }
  render(); save();
}

function dropTerm(id) {
  conn.send({ t: "kill", id });
  panes.get(id)?.dispose();
  panes.delete(id);
  delete S.terms[id];
}

function promote(id) {                                    // 자식 → 독립 그룹의 부모
  const g = groupOf(id), t = S.terms[id];
  g.children = g.children.filter(x => x !== id);
  g.visible = g.visible.filter(x => x !== id);
  const ng = { id: "g" + uid(), parentId: id, children: [], visible: [], ratio: 0.6 };
  S.groups.push(ng);
  t.groupId = ng.id; t.role = "parent"; t.hue = null;
  S.activeGroup = ng.id; S.focusedTerm = id;
  toast(`${t.name} — 독립 그룹으로 승격`);
  render(); save();
}

// ─────────────────────────────────────────────── 그리기
function renderTabs() {
  $("#tabs").innerHTML = S.groups.map(g => {
    const t = S.terms[g.parentId];
    const running = groupTerms(g).some(x => S.terms[x]?.busy);
    return `<div class="tab ${g.id === S.activeGroup ? "on" : ""}" data-id="${g.parentId}" title="${esc(t.cwd)}">
      <span class="t-ic ${running ? "run" : ""}">&#9632;</span>
      <span class="t-nm">${esc(t.name)}</span>
      ${g.children.length ? `<span class="kidcount">${g.children.length}</span>` : ""}
      <span class="x" data-x="${g.parentId}">&times;</span></div>`;
  }).join("");
}

function headHTML(t, isParent, no) {
  const kc = isParent ? "var(--acc)" : `var(--${t.hue || "cyan"})`;
  const moved = !isParent && t.cwd !== t.birthCwd;
  return { kc, html: `
    ${isParent ? "" : `<span class="kidno">${no}</span>`}
    <span class="ph-nm" title="더블클릭하면 이름을 바꿉니다">${esc(t.name)}</span>
    <span class="ph-cwd" title="${esc(t.cwd)}">${esc(isParent ? t.cwd : shortPath(t.cwd))}</span>
    ${t.busy ? '<span class="badge run" title="실행 중 — 접기에서 보호됩니다">● 실행</span>' : ""}
    ${t.dead ? '<span class="badge dead">종료됨</span>' : ""}
    ${moved ? `<span class="badge" title="태어난 곳: ${esc(t.birthCwd)}">&#10548; 이동</span>` : ""}
    ${t.fs ? `<span class="badge" title="이 창만 ${t.fs}px — Ctrl+0 으로 초기화">Aa ${t.fs}</span>` : ""}
    <span class="ph-act">
      ${isParent ? '<b class="add" data-add title="자식 터미널 추가 (Ctrl+Shift+D)">&#43;</b>' : ""}
      <b data-close title="${isParent ? "그룹 닫기" : "닫기"}">&times;</b>
    </span>` };
}

function updateHead(id) {
  const t = S.terms[id], p = panes.get(id);
  if (!t || !p) return;
  const g = groupOf(id);
  const isParent = t.role === "parent";
  const { kc, html } = headHTML(t, isParent, g.children.indexOf(id) + 1);
  p.el.style.setProperty("--kc", kc);
  p.el.querySelector(".pane-head").innerHTML = html;
}

function foldedBar(t, no) {
  const el = document.createElement("div");
  el.className = "fbar";
  el.dataset.unfold = t.id;
  el.style.setProperty("--kc", `var(--${t.hue || "cyan"})`);
  el.title = "눌러서 화면으로 되돌리기";
  el.innerHTML = `<span class="kidno">${no}</span><span class="fnm">${esc(t.name)}</span>
    <span class="fcwd">${esc(shortPath(t.cwd))}</span>
    ${t.busy ? '<span class="badge run">●</span>' : ""}<span class="fx">&#8963; 펼치기</span>`;
  return el;
}

function renderPanes() {
  const g = activeGroup();
  if (!g) return;
  const parent = S.terms[g.parentId];
  // 화면 순서는 태어난 순서를 따른다 — 접혔다 펴져도 번호가 튀지 않게
  const kids = g.children.filter(id => g.visible.includes(id)).map(id => S.terms[id]).filter(Boolean);
  const folded = g.children.filter(id => !g.visible.includes(id));

  const pp = paneOf(parent);
  pp.el.classList.add("parent");
  pp.el.style.flex = `0 0 ${Math.round(g.ratio * 100)}%`;

  const nodes = [pp.el];
  if (kids.length || folded.length) {
    const splitter = document.createElement("div");
    splitter.className = "splitter";
    splitter.addEventListener("mousedown", startDrag);
    const kidsEl = document.createElement("div");
    kidsEl.className = "kids";
    kids.forEach(t => { const p = paneOf(t); p.el.classList.remove("parent"); p.el.style.flex = ""; kidsEl.appendChild(p.el); });
    folded.forEach(id => kidsEl.appendChild(foldedBar(S.terms[id], g.children.indexOf(id) + 1)));
    nodes.push(splitter, kidsEl);
  }
  $("#panes").replaceChildren(...nodes);           // 노드를 옮기기만 한다 — xterm 은 살아남는다

  groupTerms(g).forEach(id => { if (S.terms[id]) updateHead(id); });
  document.querySelectorAll(".pane").forEach(p => p.classList.toggle("focus", p.dataset.id === S.focusedTerm));

  requestAnimationFrame(() => {
    [parent, ...kids].forEach(t => {
      const p = panes.get(t.id);
      if (!p) return;
      p.refit();
      if (!p.spawned) p.reattach();                // 있으면 붙고, 없으면 서버가 gone 을 보내 새로 띄운다
    });
  });
}

function render() { renderTabs(); renderPanes(); updateStatus(); }

function updateStatus() {
  const g = activeGroup(); if (!g) return;
  const t = S.terms[S.focusedTerm] || S.terms[g.parentId];
  $("#stPath").textContent = t.cwd;
  $("#stShell").textContent = t.shellLabel || t.shell;
  $("#stGroup").textContent = `그룹: ${S.terms[g.parentId].name} · 자식 ${g.children.length} (화면 ${g.visible.length}/${S.maxVisible})`;
}

function startDrag(e) {
  e.preventDefault();
  const g = activeGroup();
  const box = $("#panes").getBoundingClientRect();
  const move = ev => {
    g.ratio = Math.min(0.85, Math.max(0.2, (ev.clientX - box.left) / box.width));
    const p = panes.get(g.parentId);
    if (p) { p.el.style.flex = `0 0 ${Math.round(g.ratio * 100)}%`; p.refit(); }
    groupTerms(g).forEach(id => panes.get(id)?.refit());
  };
  const up = () => { removeEventListener("mousemove", move); removeEventListener("mouseup", up); save(); };
  addEventListener("mousemove", move); addEventListener("mouseup", up);
}

// ─────────────────────────────────────────────── 조작
$("#panes").addEventListener("mousedown", e => {
  const fb = e.target.closest("[data-unfold]");
  if (fb) { unfold(fb.dataset.unfold); render(); save(); return; }
  const pane = e.target.closest(".pane"); if (!pane) return;
  const id = pane.dataset.id;
  if (e.target.closest("[data-add]")) { e.stopPropagation(); const r = e.target.getBoundingClientRect(); pickFolder(id, r.left - 40, r.bottom + 4); return; }
  if (e.target.closest("[data-close]")) { e.stopPropagation(); closeTerm(id); return; }
});
$("#panes").addEventListener("dblclick", e => {
  const nm = e.target.closest(".ph-nm"); if (!nm) return;
  renamePane(nm.closest(".pane").dataset.id);
});
$("#panes").addEventListener("contextmenu", e => {
  const head = e.target.closest(".pane-head"); if (!head) return;
  e.preventDefault();
  paneMenu(head.closest(".pane").dataset.id, e.clientX, e.clientY);
});
$("#panes").addEventListener("wheel", e => {
  if (!e.ctrlKey) return;
  const pane = e.target.closest(".pane"); if (!pane) return;
  e.preventDefault();
  const t = S.terms[pane.dataset.id];
  t.fs = Math.max(FS_MIN, Math.min(FS_MAX, (t.fs || S.fontSize) + (e.deltaY < 0 ? 1 : -1)));
  panes.get(t.id).setFont(t.fs);
  updateHead(t.id); save();
}, { passive: false });

function renamePane(id) {
  const t = S.terms[id], p = panes.get(id);
  const nm = p?.el.querySelector(".ph-nm"); if (!nm) return;
  nm.innerHTML = `<input value="${esc(t.name)}">`;
  const inp = nm.querySelector("input"); inp.focus(); inp.select();
  const done = ok => { if (ok && inp.value.trim()) t.name = inp.value.trim(); updateHead(id); renderTabs(); save(); };
  inp.addEventListener("keydown", e => { e.stopPropagation(); if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); });
  inp.addEventListener("blur", () => done(true));
  inp.addEventListener("mousedown", e => e.stopPropagation());
}

$("#tabs").addEventListener("click", e => {
  const x = e.target.closest(".x"); if (x) { closeTerm(x.dataset.x); return; }
  const tab = e.target.closest(".tab"); if (!tab) return;
  S.activeGroup = groupOf(tab.dataset.id).id;
  render(); focus(tab.dataset.id);
});
$("#tabs").addEventListener("dblclick", e => {
  const tab = e.target.closest(".tab"); if (tab) { S.activeGroup = groupOf(tab.dataset.id).id; render(); renamePane(tab.dataset.id); }
});
$("#tabs").addEventListener("contextmenu", e => {
  const tab = e.target.closest(".tab"); if (!tab) return;
  e.preventDefault(); paneMenu(tab.dataset.id, e.clientX, e.clientY);
});
$("#tabadd").addEventListener("click", () => { newGroup(explorer.selected || S.home, S.defaultShell); render(); save(); });

// ⊕ — 부모의 현재 폴더 아래에서 고른다
async function pickFolder(parentId, x, y) {
  const t = S.terms[parentId], g = groupOf(parentId);
  let subs = [];
  try { subs = (await api.list(t.cwd)).entries.filter(e => e.dir && !e.hidden); } catch {}
  const items = [{ cap: `${leaf(t.cwd)} 아래에서 고르기` },
    { i: "&#128194;", t: `현재 폴더 그대로 (${leaf(t.cwd)})`, hot: true, act: () => addChild(g, t.cwd) }];
  if (subs.length) items.push({ sep: 1 });
  subs.slice(0, 20).forEach(e => items.push({ i: "&#128193;", t: e.name, act: () => addChild(g, join(t.cwd, e.name)) }));
  items.push({ sep: 1 }, { i: "&#9881;", t: "다른 셸로…", sub: SHELLS.map(([label, sh]) => ({ t: label, act: () => addChild(g, t.cwd, sh) })) });
  showMenu(x, y, items);
}

function paneMenu(id, x, y) {
  const t = S.terms[id], g = groupOf(id);
  const items = [
    { i: "&#9998;", t: "이름 바꾸기", k: "F2", act: () => renamePane(id) },
    { i: "&#128279;", t: `태어난 곳: ${leaf(t.birthCwd)}`, dis: true }
  ];
  if (t.role === "child") {
    items.push({ sep: 1 },
      { i: "&#8599;", t: "독립 그룹으로 승격", hot: true, act: () => promote(id) },
      { i: g.visible.includes(id) ? "&#8863;" : "&#8862;", t: g.visible.includes(id) ? "화면에서 접기" : "화면에 펼치기",
        act: () => { if (g.visible.includes(id)) g.visible = g.visible.filter(v => v !== id); else unfold(id); render(); save(); } });
  } else {
    items.push({ sep: 1 }, { i: "&#8627;", t: "자식 터미널 추가", hot: true, act: () => pickFolder(id, x, y) });
  }
  items.push({ sep: 1 },
    { i: "&#128449;", t: "탐색기를 이 폴더로", act: () => explorer.setRoot(t.cwd) },
    { i: "&#10005;", t: t.role === "parent" ? "그룹 닫기" : "닫기", k: "Ctrl+W", act: () => closeTerm(id) });
  showMenu(x, y, items);
}

// ─────────────────────────────────────────────── 탐색기
const explorer = createExplorer($("#tree"), {
  onSelect: p => { $("#expRoot").textContent = explorer.root; },
  onContext: (path, name, isDir, x, y) => {
    const g = activeGroup(), parent = S.terms[g.parentId];
    const dir = isDir ? path : explorer.parentOf(path);
    showMenu(x, y, [
      { i: "&#128194;", t: "열기", k: "Enter", act: () => api.open(path).catch(e => toast(e.message)) },
      { sep: 1 },
      { i: "&#8627;", t: `자식 터미널로 열기 — ${parent.name} 밑`, hot: true, act: () => addChild(g, dir) },
      { i: "&#9633;", t: "새 그룹으로 열기", sub: SHELLS.map(([label, sh]) => ({ t: label, act: () => { newGroup(dir, sh); render(); save(); } })) },
      { i: "&#128449;", t: "탐색기 루트로", act: () => explorer.setRoot(dir) },
      { sep: 1 },
      { i: "&#10010;", t: "새로 만들기", sub: [
        { t: "폴더", act: async () => { try { await api.mkdir(dir, "새 폴더"); await explorer.refresh(dir); } catch (e) { toast(e.message); } } },
        { t: "텍스트 문서", act: async () => { try { await api.newFile(dir, "새 파일.txt"); await explorer.refresh(dir); } catch (e) { toast(e.message); } } },
        { t: "PowerShell 스크립트 (.ps1)", act: async () => { try { await api.newFile(dir, "새 스크립트.ps1"); await explorer.refresh(dir); } catch (e) { toast(e.message); } } }
      ] },
      { i: "&#9986;", t: "잘라내기", k: "Ctrl+X", act: () => { clip = { path, move: true }; toast("잘라내기: " + name); } },
      { i: "&#128203;", t: "복사", k: "Ctrl+C", act: () => { clip = { path, move: false }; toast("복사: " + name); } },
      { i: "&#128204;", t: "붙여넣기", k: "Ctrl+V", dis: !clip || !isDir, act: async () => {
        try { await api.transfer([clip.path], dir, clip.move); if (clip.move) clip = null; await explorer.refresh(dir); }
        catch (e) { toast(e.message); } } },
      { sep: 1 },
      { i: "&#9998;", t: "이름 바꾸기", k: "F2", act: () => explorer.renameAt(path) },
      { i: "&#128465;", t: "삭제 (휴지통)", k: "Del", act: async () => {
        if (!confirm(`${name} 을(를) 휴지통으로 보낼까요?`)) return;
        try { await api.remove(path); await explorer.refresh(explorer.parentOf(path)); toast(name + " — 휴지통으로"); }
        catch (e) { toast(e.message); } } },
      { sep: 1 },
      { i: "&#128203;", t: "경로 복사", k: "Ctrl+Shift+C", act: () => { navigator.clipboard?.writeText(path); toast(path); } },
      { i: "&#128449;", t: "Windows 탐색기에서 표시", act: () => api.reveal(path).catch(e => toast(e.message)) },
      { i: "&#8505;", t: "속성", k: "Alt+Enter", act: () => api.properties(path).catch(e => toast(e.message)) }
    ]);
  }
});
let clip = null;

$("#expUp").addEventListener("click", () => explorer.setRoot(explorer.parentOf(explorer.root)).then(() => $("#expRoot").textContent = explorer.root));
$("#expRefresh").addEventListener("click", () => explorer.refresh());
$("#expNewDir").addEventListener("click", async () => {
  try { await api.mkdir(explorer.selected, "새 폴더"); await explorer.refresh(explorer.selected); } catch (e) { toast(e.message); }
});
$("#railExp").addEventListener("click", toggleExplorer);
function toggleExplorer() {
  S.expHidden = !S.expHidden;
  $("#exp").classList.toggle("hide", S.expHidden);
  app.dataset.layout = S.expHidden ? "term" : "ide";
  refitAll(); save();
}

// ─────────────────────────────────────────────── 테마 · 글자 크기
function setTheme(key) {
  S.theme = key;
  const xt = applyTheme(app, key);
  panes.forEach(p => p.setTheme(xt));
  save();
}
function themeMenu(x, y) {
  showMenu(x, y, [{ cap: "테마" }, ...Object.entries(THEMES).map(([k, t]) => ({ t: t.n, dot: t.acc, act: () => setTheme(k) }))]);
}
$("#btnTheme").addEventListener("click", e => { const r = e.target.getBoundingClientRect(); themeMenu(r.left - 150, r.bottom + 4); });
$("#railTheme").addEventListener("click", e => { const r = e.target.getBoundingClientRect(); themeMenu(r.right + 6, r.top); });

function setFont(delta, absolute) {
  S.fontSize = Math.max(FS_MIN, Math.min(FS_MAX, absolute !== undefined ? absolute : S.fontSize + delta));
  Object.values(S.terms).forEach(t => { t.fs = null; panes.get(t.id)?.setFont(S.fontSize); });
  $("#fsVal").textContent = S.fontSize + "px";
  Object.keys(S.terms).forEach(updateHead);
  save();
}
$("#fsUp").addEventListener("click", () => setFont(+1));
$("#fsDown").addEventListener("click", () => setFont(-1));
$("#fsVal").addEventListener("click", () => { setFont(0, FS_DEF); toast(`글자 크기 ${FS_DEF}px — 기본값`); });

// ─────────────────────────────────────────────── 검색
let findEl = null;
function openFind() {
  const p = panes.get(S.focusedTerm); if (!p) return;
  closeFind();
  findEl = document.createElement("div");
  findEl.className = "find";
  findEl.innerHTML = `<input placeholder="이 터미널에서 찾기" id="findInput"><b id="findPrev">&#8593;</b><b id="findNext">&#8595;</b><b id="findClose">&times;</b>`;
  $("#app").appendChild(findEl);
  const inp = findEl.querySelector("#findInput");
  const next = () => p.search.findNext(inp.value);
  const prev = () => p.search.findPrevious(inp.value);
  inp.addEventListener("input", next);
  inp.addEventListener("keydown", e => {
    e.stopPropagation();
    if (e.key === "Enter") (e.shiftKey ? prev : next)();
    if (e.key === "Escape") closeFind();
  });
  findEl.querySelector("#findNext").onclick = next;
  findEl.querySelector("#findPrev").onclick = prev;
  findEl.querySelector("#findClose").onclick = closeFind;
  inp.focus();
}
function closeFind() { findEl?.remove(); findEl = null; panes.get(S.focusedTerm)?.term.focus(); }
$("#btnSearch").addEventListener("click", openFind);

// ─────────────────────────────────────────────── 단축키
function isShortcut(ev) {
  if (ev.type !== "keydown") return false;
  const k = ev.key;
  if (ev.ctrlKey && ev.shiftKey && (k === "D" || k === "d" || k === "T" || k === "t")) return true;
  if (ev.ctrlKey && !ev.shiftKey && (k === "b" || k === "B" || k === "f" || k === "F")) return true;
  if (ev.ctrlKey && (k === "=" || k === "+" || k === "-" || k === "0")) return true;
  if (ev.altKey && /^[0-9]$/.test(k)) return true;
  if (k === "F2") return true;
  return false;
}

document.addEventListener("keydown", e => {
  if (!isShortcut(e)) return;
  const g = activeGroup();
  const k = e.key;

  if (e.ctrlKey && e.shiftKey && (k === "D" || k === "d")) {
    e.preventDefault();
    const pid = g.parentId;
    const anchor = panes.get(pid)?.el.querySelector("[data-add]");
    const r = anchor ? anchor.getBoundingClientRect() : { left: innerWidth / 2, bottom: 120 };
    return pickFolder(pid, r.left - 40, r.bottom + 4);
  }
  if (e.ctrlKey && e.shiftKey && (k === "T" || k === "t")) { e.preventDefault(); newGroup(explorer.selected || S.home, S.defaultShell); render(); save(); return; }
  if (e.ctrlKey && (k === "b" || k === "B")) { e.preventDefault(); return toggleExplorer(); }
  if (e.ctrlKey && (k === "f" || k === "F")) { e.preventDefault(); return openFind(); }
  if (e.ctrlKey && (k === "=" || k === "+")) { e.preventDefault(); return setFont(+1); }
  if (e.ctrlKey && k === "-") { e.preventDefault(); return setFont(-1); }
  if (e.ctrlKey && k === "0") { e.preventDefault(); toast(`글자 크기 ${FS_DEF}px — 기본값`); return setFont(0, FS_DEF); }
  if (e.altKey && /^[1-9]$/.test(k)) {
    const id = g.children[Number(k) - 1];
    if (id) { e.preventDefault(); unfold(id); render(); save(); }
    return;
  }
  if (e.altKey && k === "0") { e.preventDefault(); return focus(g.parentId); }
  if (k === "F2") { e.preventDefault(); return renamePane(S.focusedTerm); }
});

addEventListener("resize", refitAll);
function refitAll() { requestAnimationFrame(() => panes.forEach(p => p.refit())); }

// ─────────────────────────────────────────────── 작업셋 저장 (자동)
let saveTimer = null;
function save() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const terms = {};
    for (const [id, t] of Object.entries(S.terms))
      terms[id] = { id, groupId: t.groupId, role: t.role, name: t.name, cwd: t.cwd,
                    birthCwd: t.birthCwd, shell: t.shell, hue: t.hue, fs: t.fs };
    api.saveWs({
      v: 1, theme: S.theme, layout: app.dataset.layout, maxVisible: S.maxVisible, fontSize: S.fontSize,
      expHidden: S.expHidden, explorerRoot: explorer.root, activeGroup: S.activeGroup,
      groups: S.groups.map(g => ({ ...g })), terms
    }).catch(() => {});
  }, 500);
}

function restore(w) {
  if (!w || !w.groups?.length || !w.terms) return false;
  S.theme = w.theme || S.theme;
  S.maxVisible = w.maxVisible || S.maxVisible;
  S.fontSize = w.fontSize || S.fontSize;
  S.expHidden = !!w.expHidden;
  for (const t of Object.values(w.terms)) {
    mkTerm({ id: t.id, groupId: t.groupId, role: t.role, name: t.name, cwd: t.cwd,
             birthCwd: t.birthCwd, shell: t.shell, hue: t.hue, fs: t.fs });
  }
  S.groups = w.groups.filter(g => S.terms[g.parentId]).map(g => ({
    id: g.id, parentId: g.parentId, ratio: g.ratio || 0.6,
    children: (g.children || []).filter(id => S.terms[id]),
    visible: (g.visible || []).filter(id => S.terms[id])
  }));
  if (!S.groups.length) return false;
  S.groups.forEach(g => enforceVisible(g, true));
  S.activeGroup = S.groups.find(g => g.id === w.activeGroup)?.id || S.groups[0].id;
  S.focusedTerm = S.terms[activeGroup().parentId].id;
  return true;
}

// ─────────────────────────────────────────────── 시작
(async function boot() {
  try {
    const env = await api.env();
    S.home = env.home; S.platform = env.platform; S.defaultShell = env.defaultShell || "pwsh";
  } catch (e) {
    document.body.innerHTML = `<div style="padding:24px; font-family:sans-serif">
      서버에 연결하지 못했습니다.<br><br>서버를 띄운 창에 찍힌 주소(토큰 포함)로 다시 들어오세요.<br><code>${esc(e.message)}</code></div>`;
    return;
  }

  let w = null;
  try { w = (await api.loadWs()).workspace; } catch {}
  if (!restore(w)) newGroup(S.home, S.defaultShell);

  applyTheme(app, S.theme);
  $("#fsVal").textContent = S.fontSize + "px";
  app.dataset.layout = S.expHidden ? "term" : "ide";
  $("#exp").classList.toggle("hide", S.expHidden);

  conn.connect({
    onStatus: st => {
      const el = $("#stConn");
      el.textContent = st === "ok" ? "연결됨" : "연결 끊김 — 다시 붙는 중";
      el.className = "conn " + st;
    },
    onOpen: () => { panes.forEach(p => p.reattach()); }
  });

  const root = w?.explorerRoot || S.home;
  await explorer.setRoot(root);
  $("#expRoot").textContent = explorer.root;

  render();
  focus(S.focusedTerm);

  // 문제가 생겼을 때 콘솔에서 들여다볼 수 있는 창구
  window.poshdeck = { S, panes, api, render, save,
    text: id => { const p = panes.get(id || S.focusedTerm); if (!p) return "";
      const b = p.term.buffer.active, out = [];
      for (let i = 0; i < b.length; i++) out.push(b.getLine(i)?.translateToString(true) ?? "");
      return out.join("\n").replace(/\n{3,}/g, "\n\n").trim(); } };
})();
