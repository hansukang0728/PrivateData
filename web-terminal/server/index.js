// PoshDeck — 127.0.0.1 에만 뜨는 로컬 에이전트. Chrome 이 UI, 여기가 손발.
import express from "express";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { spawn as spawnProc } from "node:child_process";
import { fileURLToPath } from "node:url";
import { WebSocketServer } from "ws";

import { TOKEN, gate, checkUpgrade } from "./security.js";
import * as ptylib from "./pty.js";
import * as fsapi from "./fsapi.js";
import * as shellops from "./shellops.js";
import * as ws from "./workspace.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, "..");
const CFG = ws.config();
const NO_OPEN = process.argv.includes("--no-open");

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "2mb" }));

let PORT = Number(process.env.PORT) || CFG.port || 7788;
app.use((req, res, next) => gate(PORT)(req, res, next));

const vendor = (name, sub) => express.static(path.join(ROOT, "node_modules", name, sub));
app.use("/vendor/xterm", vendor("@xterm/xterm", ""));
app.use("/vendor/addon-fit", vendor("@xterm/addon-fit", "lib"));
app.use("/vendor/addon-search", vendor("@xterm/addon-search", "lib"));
app.use("/vendor/addon-webgl", vendor("@xterm/addon-webgl", "lib"));
app.use("/vendor/addon-unicode11", vendor("@xterm/addon-unicode11", "lib"));
app.use(express.static(path.join(ROOT, "web"), { index: "index.html" }));

const ok = (res, body) => res.json({ ok: true, ...body });
const fail = (res, e) => res.status(400).json({ ok: false, error: e.message || String(e) });
const guard = p => fsapi.guard(p, CFG.roots);

app.get("/api/env", (req, res) => ok(res, {
  home: os.homedir(), platform: process.platform, defaultShell: CFG.defaultShell,
  roots: CFG.roots, sessions: [...ptylib.sessions.keys()]
}));

app.get("/api/fs/drives", async (req, res) => { try { ok(res, { drives: await fsapi.drives() }); } catch (e) { fail(res, e); } });
app.get("/api/fs/list", async (req, res) => { try { ok(res, await fsapi.list(guard(req.query.path || os.homedir()))); } catch (e) { fail(res, e); } });

app.post("/api/fs/mkdir",    async (req, res) => { try { ok(res, { path: await fsapi.mkdir(guard(req.body.dir), req.body.name) }); } catch (e) { fail(res, e); } });
app.post("/api/fs/newfile",  async (req, res) => { try { ok(res, { path: await fsapi.newFile(guard(req.body.dir), req.body.name) }); } catch (e) { fail(res, e); } });
app.post("/api/fs/rename",   async (req, res) => { try { ok(res, { path: await fsapi.rename(guard(req.body.from), req.body.to) }); } catch (e) { fail(res, e); } });
app.post("/api/fs/delete",   async (req, res) => { try { ok(res, await fsapi.remove(guard(req.body.path), !!req.body.permanent)); } catch (e) { fail(res, e); } });
app.post("/api/fs/transfer", async (req, res) => {
  try { ok(res, { paths: await fsapi.transfer((req.body.sources || []).map(guard), guard(req.body.dest), !!req.body.move) }); }
  catch (e) { fail(res, e); }
});

app.post("/api/shell/open",       (req, res) => { try { shellops.openDefault(guard(req.body.path)); ok(res, {}); } catch (e) { fail(res, e); } });
app.post("/api/shell/reveal",     (req, res) => { try { shellops.reveal(guard(req.body.path)); ok(res, {}); } catch (e) { fail(res, e); } });
app.post("/api/shell/properties", (req, res) => { try { shellops.properties(guard(req.body.path)); ok(res, {}); } catch (e) { fail(res, e); } });

app.get("/api/workspace",  (req, res) => ok(res, { workspace: ws.load() }));
app.post("/api/workspace", (req, res) => ok(res, { saved: ws.save(req.body) }));

const server = http.createServer(app);
const wss = new WebSocketServer({ noServer: true });

server.on("upgrade", (req, socket, head) => {
  if (!checkUpgrade(req, PORT)) { socket.write("HTTP/1.1 401 Unauthorized\r\n\r\n"); socket.destroy(); return; }
  wss.handleUpgrade(req, socket, head, sock => wss.emit("connection", sock, req));
});

wss.on("connection", sock => {
  const mine = new Map();                                    // id -> 이 연결이 붙인 리스너
  const send = msg => { if (sock.readyState === 1) sock.send(JSON.stringify(msg)); };

  const bind = id => {
    if (mine.has(id)) return;
    const fn = msg => send(msg);
    const info = ptylib.attach(id, fn);
    if (!info) { send({ t: "gone", id }); return; }
    mine.set(id, fn);
    send({ t: "attached", id, buffer: info.buffer, cwd: info.cwd, busy: info.busy, shellLabel: info.shellLabel });
  };

  sock.on("message", raw => {
    let m; try { m = JSON.parse(raw); } catch { return; }
    try {
      switch (m.t) {
        case "spawn": {
          const cwd = m.cwd ? guard(m.cwd) : os.homedir();
          ptylib.spawn({ id: m.id, cwd, shell: m.shell || CFG.defaultShell, cols: m.cols, rows: m.rows });
          bind(m.id);
          break;
        }
        case "attach": bind(m.id); break;
        case "in":     ptylib.write(m.id, m.d); break;
        case "resize": ptylib.resize(m.id, m.cols, m.rows); break;
        case "kill":   ptylib.kill(m.id); break;
      }
    } catch (e) {
      send({ t: "error", id: m.id, message: e.message });
    }
  });

  sock.on("close", () => { for (const [id, fn] of mine) ptylib.detach(id, fn); mine.clear(); });
});

function listen(port, tries = 0) {
  server.once("error", err => {
    if (err.code === "EADDRINUSE" && tries < 20) { listen(port + 1, tries + 1); return; }
    console.error("[PoshDeck] 서버를 띄우지 못했습니다:", err.message);
    process.exit(1);
  });
  server.listen(port, "127.0.0.1", () => {
    PORT = port;
    const url = `http://127.0.0.1:${port}/?token=${TOKEN}`;
    console.log("");
    console.log("  PoshDeck 가 떴습니다.");
    console.log("  " + url);
    console.log("");
    console.log("  이 주소에는 1회용 토큰이 들어 있습니다. 다른 사람에게 주지 마세요.");
    console.log("  종료하려면 이 창에서 Ctrl+C.");
    console.log("");
    if (!NO_OPEN) openBrowser(url);
  });
}

function openBrowser(url) {
  try {
    if (process.platform === "win32") spawnProc("cmd.exe", ["/c", "start", "", url], { detached: true, stdio: "ignore", windowsHide: true }).unref();
    else if (process.platform === "darwin") spawnProc("open", [url], { detached: true, stdio: "ignore" }).unref();
    else spawnProc("xdg-open", [url], { detached: true, stdio: "ignore" }).unref();
  } catch { /* 못 열면 위 주소를 직접 붙여넣으면 된다 */ }
}

for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => { console.log("\n[PoshDeck] 세션을 정리하고 종료합니다."); ptylib.killAll(); process.exit(0); });
}

listen(PORT);
