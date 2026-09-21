"""RFC 6455 WebSocket — 표준 라이브러리만으로. 설치할 게 없어야 해서 직접 짰다."""
import base64, hashlib, struct, threading

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


def accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key + GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


class WSConn:
    """한 연결. send 는 여러 스레드가 부르므로 잠금이 필요하다."""

    def __init__(self, sock, rfile=None):
        self.sock = sock
        self.rfile = rfile          # HTTP 핸들러가 이미 버퍼에 읽어둔 바이트가 있을 수 있다
        self._send_lock = threading.Lock()
        self.closed = False

    # ── 보내기 ─────────────────────────────────────────────
    def send_text(self, text: str):
        self._send(OP_TEXT, text.encode("utf-8"))

    def _send(self, opcode: int, payload: bytes):
        with self._send_lock:
            if self.closed:
                return
            n = len(payload)
            header = bytearray([0x80 | opcode])
            if n < 126:
                header.append(n)
            elif n < 65536:
                header.append(126)
                header += struct.pack(">H", n)
            else:
                header.append(127)
                header += struct.pack(">Q", n)
            try:
                self.sock.sendall(bytes(header) + payload)
            except OSError:
                self.closed = True

    def close(self):
        if not self.closed:
            self._send(OP_CLOSE, b"")
            self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass

    # ── 받기 ───────────────────────────────────────────────
    def _read_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.rfile.read(n - len(buf)) if self.rfile else self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("closed")
            buf += chunk
        return buf

    def recv_text(self):
        """텍스트 메시지 하나를 돌려준다. 끊기면 None."""
        frags, frag_op = [], None
        while True:
            try:
                b0, b1 = self._read_exact(2)
            except (ConnectionError, OSError):
                self.closed = True
                return None
            fin, opcode = b0 & 0x80, b0 & 0x0F
            masked, length = b1 & 0x80, b1 & 0x7F
            try:
                if length == 126:
                    length = struct.unpack(">H", self._read_exact(2))[0]
                elif length == 127:
                    length = struct.unpack(">Q", self._read_exact(8))[0]
                if length > 16 * 1024 * 1024:            # 터무니없는 프레임은 끊는다
                    self.close(); return None
                mask = self._read_exact(4) if masked else None
                payload = self._read_exact(length) if length else b""
            except (ConnectionError, OSError):
                self.closed = True
                return None
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

            if opcode == OP_CLOSE:
                self.close(); return None
            if opcode == OP_PING:
                self._send(OP_PONG, payload); continue
            if opcode == OP_PONG:
                continue

            if opcode == OP_CONT:
                frags.append(payload)
            else:
                frag_op, frags = opcode, [payload]
            if fin:
                data = b"".join(frags)
                frags = []
                if frag_op == OP_TEXT:
                    return data.decode("utf-8", "replace")
                # 바이너리는 쓰지 않는다
