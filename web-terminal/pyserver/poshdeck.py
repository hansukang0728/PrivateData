"""PoshDeck — Python 표준 라이브러리만으로 도는 로컬 에이전트.

설치할 패키지가 하나도 없다. 실행:  py pyserver\\poshdeck.py
"""
import json
import mimetypes
import os
import secrets
import socket
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsops                     # noqa: E402
import sessions                  # noqa: E402
import wsproto                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
TOKEN = secrets.token_hex(24)
COOKIE = "poshdeck_token"
NO_OPEN = "--no-open" in sys.argv
PORT = 7788

DEFAULT_CONFIG = {"roots": [], "defaultShell": "pwsh", "port": 7788}


def config_path():
    return os.path.join(sessions.data_dir(), "config.json")


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(config_path(), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


CFG = load_config()


def ws_path():
    return os.path.join(sessions.data_dir(), "workspace.json")


def load_workspace():
    try:
        with open(ws_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_workspace(state):
    try:
        with open(ws_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except OSError as e:
        print("[PoshDeck] 작업셋 저장 실패:", e)
        return False


def guard(path):
    return fsops.guard(path, CFG.get("roots") or [])


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PoshDeck"

    def log_message(self, fmt, *args):
        pass                                               # 콘솔은 조용하게

    # ── 인증 ───────────────────────────────────────────────
    def _token(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        tok = (qs.get("token") or [None])[0]
        if not tok:
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == COOKIE:
                    tok = v
        return tok

    def _authed(self):
        tok = self._token()
        return bool(tok) and secrets.compare_digest(tok, TOKEN)

    def _origin_ok(self):
        origin = self.headers.get("Origin")
        return (not origin) or origin in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")

    # ── 응답 헬퍼 ──────────────────────────────────────────
    def _send(self, body, ctype="text/plain; charset=utf-8", code=200, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8", code)

    def _ok(self, **kw):
        self._json({"ok": True, **kw})

    def _fail(self, err):
        self._json({"ok": False, "error": str(err)}, 400)

    # ── GET ────────────────────────────────────────────────
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)

        if path == "/ws":
            if not self._authed() or not self._origin_ok():
                self._send("401", code=401)
                return
            self._websocket()
            return

        if not self._authed():
            self._send("<h1>401</h1><p>토큰이 없거나 맞지 않습니다. 서버를 띄운 창에 찍힌 주소로 다시 들어오세요.</p>",
                       "text/html; charset=utf-8", 401)
            return

        # 첫 방문은 ?token= 으로 들어온다. 쿠키로 굳히고 깨끗한 주소로 보낸다.
        if "token" in qs and path == "/":
            self._send("", "text/html; charset=utf-8", 302,
                       {"Location": "/", "Set-Cookie": f"{COOKIE}={TOKEN}; HttpOnly; SameSite=Strict; Path=/"})
            return

        if path.startswith("/api/"):
            self._api_get(path, qs)
            return

        self._static(path)

    def _static(self, path):
        rel = path.lstrip("/") or "index.html"
        full = os.path.abspath(os.path.join(WEB, rel))
        if not full.startswith(WEB) or not os.path.isfile(full):
            self._send("404 Not Found", code=404)
            return
        ctype, _ = mimetypes.guess_type(full)
        if full.endswith(".js"):
            ctype = "text/javascript; charset=utf-8"
        elif full.endswith(".css"):
            ctype = "text/css; charset=utf-8"
        elif full.endswith(".html"):
            ctype = "text/html; charset=utf-8"
        with open(full, "rb") as f:
            self._send(f.read(), ctype or "application/octet-stream")

    def _api_get(self, path, qs):
        try:
            if path == "/api/env":
                self._ok(home=os.path.expanduser("~"), platform=sys.platform,
                         defaultShell=CFG.get("defaultShell", "pwsh"), roots=CFG.get("roots") or [],
                         sessions=list(sessions.sessions.keys()), backend="python")
            elif path == "/api/fs/drives":
                self._ok(drives=fsops.drives())
            elif path == "/api/fs/list":
                target = guard((qs.get("path") or [os.path.expanduser("~")])[0])
                self._ok(**fsops.listdir(target))
            elif path == "/api/workspace":
                self._ok(workspace=load_workspace())
            else:
                self._send("404", code=404)
        except Exception as e:
            self._fail(e)

    # ── POST ───────────────────────────────────────────────
    def do_POST(self):
        if not self._authed():
            self._send("401", code=401)
            return
        if not self._origin_ok():
            self._json({"ok": False, "error": "origin_rejected"}, 403)
            return
        path = urllib.parse.urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._fail("본문을 읽지 못했습니다")
            return

        try:
            if path == "/api/fs/mkdir":
                self._ok(path=fsops.mkdir(guard(body["dir"]), body.get("name")))
            elif path == "/api/fs/newfile":
                self._ok(path=fsops.new_file(guard(body["dir"]), body.get("name")))
            elif path == "/api/fs/rename":
                self._ok(path=fsops.rename(guard(body["from"]), body["to"]))
            elif path == "/api/fs/delete":
                self._ok(**fsops.remove(guard(body["path"]), bool(body.get("permanent"))))
            elif path == "/api/fs/transfer":
                srcs = [guard(p) for p in body.get("sources", [])]
                self._ok(paths=fsops.transfer(srcs, guard(body["dest"]), bool(body.get("move"))))
            elif path == "/api/shell/open":
                fsops.open_default(guard(body["path"])); self._ok()
            elif path == "/api/shell/reveal":
                fsops.reveal(guard(body["path"])); self._ok()
            elif path == "/api/shell/properties":
                fsops.properties(guard(body["path"])); self._ok()
            elif path == "/api/shell/menu":
                # 탐색기가 보여주는 진짜 셸 메뉴 (TortoiseGit 같은 확장 포함)
                if sys.platform != "win32":
                    self._fail("Windows 에서만 됩니다")
                else:
                    try:
                        import shellmenu
                    except Exception as e:
                        self._fail(f"셸 메뉴 모듈을 불러오지 못했습니다: {e}")
                        return
                    err = shellmenu.show_async(guard(body["path"]),
                                               body.get("x", 0), body.get("y", 0),
                                               bool(body.get("extended")))
                    self._json({"ok": not err, "error": err} if err else {"ok": True})
            elif path == "/api/workspace":
                self._ok(saved=save_workspace(body))
            else:
                self._send("404", code=404)
        except Exception as e:
            self._fail(e)

    # ── WebSocket ──────────────────────────────────────────
    def _websocket(self):
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self._send("400", code=400)
            return
        self.close_connection = True
        try:
            self.wfile.write(("HTTP/1.1 101 Switching Protocols\r\n"
                              "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                              f"Sec-WebSocket-Accept: {wsproto.accept_key(key)}\r\n\r\n").encode())
            self.wfile.flush()
        except OSError:
            return

        ws = wsproto.WSConn(self.connection, self.rfile)
        mine = {}                                          # sid -> 이 연결이 붙인 리스너

        def send(msg):
            ws.send_text(json.dumps(msg, ensure_ascii=False))

        def bind(sid):
            if sid in mine:
                return
            s = sessions.get(sid)
            if not s:
                send({"t": "gone", "id": sid})
                return
            fn = send
            info = s.attach(fn)
            mine[sid] = fn
            send({"t": "attached", "id": sid, **info})

        try:
            while True:
                text = ws.recv_text()
                if text is None:
                    break
                try:
                    m = json.loads(text)
                except ValueError:
                    continue
                sid = m.get("id")
                try:
                    kind = m.get("t")
                    if kind == "spawn":
                        cwd = guard(m.get("cwd") or os.path.expanduser("~"))
                        sessions.spawn(sid, cwd, m.get("shell") or CFG.get("defaultShell", "pwsh"),
                                       m.get("cols", 80), m.get("rows", 24))
                        bind(sid)
                    elif kind == "attach":
                        bind(sid)
                    elif kind == "in":
                        s = sessions.get(sid)
                        if s:
                            s.write(m.get("d", ""))
                    elif kind == "resize":
                        s = sessions.get(sid)
                        if s:
                            s.resize(m.get("cols"), m.get("rows"))
                    elif kind == "kill":
                        sessions.kill(sid)
                except Exception as e:
                    send({"t": "error", "id": sid, "message": str(e)})
        finally:
            for sid, fn in mine.items():
                s = sessions.get(sid)
                if s:
                    s.detach(fn)
            ws.close()


def free_port(start):
    for p in range(start, start + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def main():
    global PORT
    PORT = free_port(int(os.environ.get("PORT") or CFG.get("port") or 7788))
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{PORT}/?token={TOKEN}"

    print()
    print("  PoshDeck 가 떴습니다.  (Python 백엔드 — 설치한 패키지 없음)")
    print("  " + url)
    print()
    print("  이 주소에는 1회용 토큰이 들어 있습니다. 다른 사람에게 주지 마세요.")
    print("  종료하려면 이 창에서 Ctrl+C.")
    print()
    if not NO_OPEN:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[PoshDeck] 세션을 정리하고 종료합니다.")
    finally:
        sessions.kill_all()
        httpd.server_close()


if __name__ == "__main__":
    main()
