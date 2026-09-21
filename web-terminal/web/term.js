// 페인 하나 = xterm 하나 + 헤더. DOM 노드는 만든 뒤 계속 재사용한다(다시 만들면 세션 화면이 날아간다).
import * as conn from "./conn.js";
import { toast } from "./menu.js";

export function createPane(t, hooks) {
  const el = document.createElement("div");
  el.className = "pane";
  el.dataset.id = t.id;
  el.innerHTML = `<div class="pane-head"></div><div class="host"></div>`;
  const host = el.querySelector(".host");

  const term = new Terminal({
    fontFamily: '"Cascadia Mono", "JetBrains Mono", D2Coding, Consolas, ui-monospace, monospace',
    fontSize: t.fs || hooks.fontSize(),
    lineHeight: 1.2,
    cursorBlink: true,
    scrollback: 10000,
    allowProposedApi: true,
    theme: hooks.theme(),
    windowsPty: hooks.isWindows() ? { backend: "conpty" } : undefined
  });

  const fit = new FitAddon.FitAddon();
  const search = new SearchAddon.SearchAddon();
  term.loadAddon(fit);
  term.loadAddon(search);
  try {
    term.loadAddon(new Unicode11Addon.Unicode11Addon());
    term.unicode.activeVersion = "11";           // 한글 폭을 제대로 계산하려면 필요하다
  } catch {}

  term.open(host);
  try { term.loadAddon(new WebglAddon.WebglAddon()); } catch { /* 없으면 캔버스로 */ }

  term.onData(d => conn.send({ t: "in", id: t.id, d }));
  term.onResize(({ cols, rows }) => conn.send({ t: "resize", id: t.id, cols, rows }));
  term.attachCustomKeyEventHandler(ev => !hooks.isShortcut(ev));   // 앱 단축키는 셸로 내려보내지 않는다
  el.addEventListener("mousedown", () => hooks.onFocus(t.id));

  let spawned = false;
  conn.route(t.id, msg => {
    switch (msg.t) {
      case "attached":
        spawned = true;
        if (msg.buffer) term.write(msg.buffer);
        t.cwd = msg.cwd || t.cwd; t.busy = !!msg.busy; t.shellLabel = msg.shellLabel;
        hooks.onState(t.id);
        break;
      case "gone":                                   // 서버에 세션이 없다 = 새로 띄워야 한다
        spawn();
        break;
      case "out":  term.write(msg.d); break;
      case "state":
        t.busy = !!msg.busy;
        if (msg.cwd && msg.cwd !== t.cwd) { t.cwd = msg.cwd; }
        hooks.onState(t.id);
        break;
      case "exit":
        t.dead = true; t.busy = false;
        term.write(`\r\n\x1b[2m[세션이 종료되었습니다 (코드 ${msg.code}). 탭을 닫거나 Ctrl+Shift+T 로 새로 여세요.]\x1b[0m\r\n`);
        hooks.onState(t.id);
        break;
      case "error": toast(msg.message); break;
    }
  });

  function spawn() {
    spawned = true;
    conn.send({ t: "spawn", id: t.id, cwd: t.cwd, shell: t.shell, cols: term.cols, rows: term.rows });
  }
  function reattach() { conn.send({ t: "attach", id: t.id }); }

  function refit() {
    if (!el.isConnected || !el.offsetHeight) return;
    try { fit.fit(); } catch {}
  }
  function setFont(px) { term.options.fontSize = px; refit(); }
  function setTheme(theme) { term.options.theme = theme; }
  function dispose() { conn.unroute(t.id); try { term.dispose(); } catch {} el.remove(); }

  return { el, host, term, fit, search, refit, setFont, setTheme, spawn, reattach, dispose,
           get spawned() { return spawned; } };
}
