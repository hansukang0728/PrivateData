"""셸 세션 — 띄우고, 출력을 나눠주고, "지금 바쁜가 / 어디인가"를 추적한다."""
import codecs
import os
import re
import sys
import threading
import time

IS_WIN = sys.platform == "win32"

OSC_DONE = re.compile("\x1b\\]633;D\x07")                  # 프롬프트가 그려졌다 = 명령이 끝났다
OSC_CWD = re.compile("\x1b\\]633;P;Cwd=(.*?)\x07")         # 프롬프트가 알려주는 현재 폴더
BUF_MAX = 256 * 1024                                       # 재접속용 출력 보관량
IDLE_SEC = 0.6                                             # 표시를 못 쓰는 셸(cmd/wsl)용 대략 판정

sessions = {}
_lock = threading.Lock()


def data_dir():
    base = os.environ.get("LOCALAPPDATA") if IS_WIN else os.path.join(os.path.expanduser("~"), ".local", "share")
    d = os.path.join(base or os.path.expanduser("~"), "poshdeck")
    os.makedirs(d, exist_ok=True)
    return d


def ps_init_file():
    """PowerShell 이 프롬프트마다 상태를 알려주도록 초기화 스크립트를 깔아둔다."""
    path = os.path.join(data_dir(), "psinit.ps1")
    body = "\r\n".join([
        "# PoshDeck 초기화 — 지우면 다시 생성됩니다",
        "try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}",
        "try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}",
        "function global:prompt {",
        "  $esc = [char]27; $bel = [char]7",
        "  $loc = $executionContext.SessionState.Path.CurrentLocation",
        "  $mark = \"$esc]633;D$bel$esc]633;P;Cwd=$($loc.Path)$bel\"",
        "  $mark + 'PS ' + $loc.Path + ('>' * ($nestedPromptLevel + 1)) + ' '",
        "}",
    ])
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    except OSError:
        pass
    return path


def _q(s):
    return f'"{s}"'


def resolve_shell(kind):
    if not IS_WIN:
        shell = os.environ.get("SHELL", "/bin/bash")
        return {"argv": [shell, "-i"], "marker": False, "label": os.path.basename(shell)}

    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    init = ps_init_file()
    if kind == "powershell":
        exe = os.path.join(sysroot, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        return {"cmdline": f"{_q(exe)} -NoLogo -NoExit -ExecutionPolicy Bypass -File {_q(init)}",
                "marker": True, "label": "Windows PowerShell"}
    if kind == "cmd":
        exe = os.environ.get("ComSpec", os.path.join(sysroot, "System32", "cmd.exe"))
        return {"cmdline": f"{_q(exe)} /K chcp 65001 >nul", "marker": False, "label": "cmd"}
    if kind == "wsl":
        return {"cmdline": "wsl.exe", "marker": False, "label": "WSL"}

    candidates = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "PowerShell", "7", "pwsh.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "pwsh.exe"),
    ]
    exe = next((p for p in candidates if p and os.path.exists(p)), "pwsh.exe")
    return {"cmdline": f"{_q(exe)} -NoLogo -NoExit -ExecutionPolicy Bypass -File {_q(init)}",
            "marker": True, "label": "PowerShell 7"}


class Session:
    def __init__(self, sid, cwd, shell="pwsh", cols=80, rows=24):
        info = resolve_shell(shell)
        if not os.path.isdir(cwd):
            cwd = os.path.expanduser("~")

        env = dict(os.environ, TERM="xterm-256color", POSHDECK="1")
        if IS_WIN:
            import ptyconpty
            self.pty = ptyconpty.ConPty(info["cmdline"], cwd, env, cols, rows)
        else:
            import ptyposix
            self.pty = ptyposix.PosixPty(info["argv"], cwd, env, cols, rows)

        self.id = sid
        self.shell = shell
        self.shell_label = info["label"]
        self.marker = info["marker"]
        self.cwd = cwd
        self.busy = False
        self.exited = False
        self.last_out = time.time()
        self.listeners = set()
        self._buf = []
        self._bytes = 0
        self._tail = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        threading.Thread(target=self._reader, daemon=True, name=f"pty-{sid[:8]}").start()

    # ── 안쪽 ────────────────────────────────────────────────
    def _emit(self, msg):
        for fn in list(self.listeners):
            try:
                fn(msg)
            except Exception:
                pass

    def _remember(self, text):
        self._buf.append(text)
        self._bytes += len(text)
        while self._bytes > BUF_MAX and len(self._buf) > 1:
            self._bytes -= len(self._buf.pop(0))

    def _set_busy(self, busy):
        if self.busy == busy:
            return
        self.busy = busy
        self._emit({"t": "state", "id": self.id, "busy": busy, "cwd": self.cwd})

    def _reader(self):
        while True:
            raw = self.pty.read()
            if not raw:
                break
            text = self._decoder.decode(raw)
            if not text:
                continue
            self._remember(text)
            self.last_out = time.time()

            hay = self._tail + text                        # 시퀀스가 청크 경계에서 잘릴 수 있다
            found = OSC_CWD.findall(hay)
            if found and found[-1] != self.cwd:
                self.cwd = found[-1]
                self._emit({"t": "state", "id": self.id, "busy": self.busy, "cwd": self.cwd})
            if self.marker and OSC_DONE.search(hay):
                self._set_busy(False)
            self._tail = hay[-512:]
            self._emit({"t": "out", "id": self.id, "d": text})

        code = self.pty.wait()
        self.exited = True
        self._emit({"t": "exit", "id": self.id, "code": code})
        with _lock:
            sessions.pop(self.id, None)

    # ── 바깥쪽 ──────────────────────────────────────────────
    def write(self, data: str):
        if self.exited:
            return
        if "\r" in data:                                   # 엔터를 쳤다 = 뭔가 돌기 시작했다
            self._set_busy(True)
        self.pty.write(data.encode("utf-8"))

    def resize(self, cols, rows):
        if not self.exited:
            self.pty.resize(int(cols or 80), int(rows or 24))

    def kill(self):
        try:
            self.pty.kill()
        except Exception:
            pass

    def attach(self, fn):
        self.listeners.add(fn)
        return {"buffer": "".join(self._buf), "cwd": self.cwd, "busy": self.busy, "shellLabel": self.shell_label}

    def detach(self, fn):
        self.listeners.discard(fn)


def spawn(sid, cwd, shell="pwsh", cols=80, rows=24):
    with _lock:
        if sid in sessions:
            return sessions[sid]
        s = Session(sid, cwd, shell, cols, rows)
        sessions[sid] = s
        return s


def get(sid):
    return sessions.get(sid)


def kill(sid):
    with _lock:
        s = sessions.pop(sid, None)
    if s:
        s.kill()


def kill_all():
    for sid in list(sessions):
        kill(sid)


def _idle_watch():
    """표시를 못 쓰는 셸은 잠잠해지면 끝난 걸로 본다."""
    while True:
        time.sleep(0.2)
        now = time.time()
        for s in list(sessions.values()):
            if not s.marker and s.busy and now - s.last_out > IDLE_SEC:
                s._set_busy(False)


threading.Thread(target=_idle_watch, daemon=True, name="idle-watch").start()
