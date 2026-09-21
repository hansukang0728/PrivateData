"""개발용(리눅스·맥) PTY. 윈도우에서는 ptyconpty 를 쓴다."""
import fcntl, os, pty, signal, struct, termios


class PosixPty:
    def __init__(self, argv, cwd, env, cols, rows):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:                                   # 자식
            try:
                os.chdir(cwd)
            except OSError:
                pass
            os.execvpe(argv[0], argv, env)
            os._exit(127)
        self.resize(cols, rows)
        self._exit_code = None

    def read(self, n=65536) -> bytes:
        try:
            return os.read(self.fd, n)
        except OSError:
            return b""

    def write(self, data: bytes):
        try:
            os.write(self.fd, data)
        except OSError:
            pass

    def resize(self, cols, rows):
        try:
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        except OSError:
            pass

    def kill(self):
        try:
            os.kill(self.pid, signal.SIGHUP)
        except OSError:
            pass

    def wait(self) -> int:
        try:
            _, status = os.waitpid(self.pid, 0)
            self._exit_code = os.waitstatus_to_exitcode(status)
        except (ChildProcessError, OSError):
            self._exit_code = -1
        try:
            os.close(self.fd)
        except OSError:
            pass
        return self._exit_code
