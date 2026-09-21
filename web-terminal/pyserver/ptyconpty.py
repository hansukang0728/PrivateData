"""Windows ConPTY — kernel32 를 ctypes 로 직접 부른다. 설치할 확장 모듈이 없다.

Windows 10 1809(빌드 17763) 이상에서 동작한다. 그 아래면 CreatePseudoConsole 이
없어서 ImportError 를 낸다 — 호출 쪽에서 파이프 모드로 떨어진다.
"""
import ctypes
import ctypes.wintypes as wt
import msvcrt
import os

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

if not hasattr(kernel32, "CreatePseudoConsole"):
    raise ImportError("이 Windows 에는 ConPTY(CreatePseudoConsole)가 없습니다. Windows 10 1809 이상이 필요합니다.")

HPCON = wt.HANDLE
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
INFINITE = 0xFFFFFFFF


class COORD(ctypes.Structure):
    _fields_ = [("X", wt.SHORT), ("Y", wt.SHORT)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR), ("lpTitle", wt.LPWSTR),
        ("dwX", wt.DWORD), ("dwY", wt.DWORD), ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD),
        ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD), ("dwFillAttribute", wt.DWORD),
        ("dwFlags", wt.DWORD), ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wt.HANDLE), ("hStdOutput", wt.HANDLE), ("hStdError", wt.HANDLE),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE),
                ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]


kernel32.CreatePseudoConsole.argtypes = [COORD, wt.HANDLE, wt.HANDLE, wt.DWORD, ctypes.POINTER(HPCON)]
kernel32.CreatePseudoConsole.restype = ctypes.c_long
kernel32.ResizePseudoConsole.argtypes = [HPCON, COORD]
kernel32.ResizePseudoConsole.restype = ctypes.c_long
kernel32.ClosePseudoConsole.argtypes = [HPCON]
kernel32.ClosePseudoConsole.restype = None
kernel32.CreatePipe.argtypes = [ctypes.POINTER(wt.HANDLE), ctypes.POINTER(wt.HANDLE), ctypes.c_void_p, wt.DWORD]
kernel32.CreatePipe.restype = wt.BOOL
kernel32.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.c_size_t)]
kernel32.InitializeProcThreadAttributeList.restype = wt.BOOL
kernel32.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
kernel32.UpdateProcThreadAttribute.restype = wt.BOOL
kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
kernel32.CreateProcessW.argtypes = [wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.BOOL,
                                    wt.DWORD, ctypes.c_void_p, wt.LPCWSTR,
                                    ctypes.POINTER(STARTUPINFOEXW), ctypes.POINTER(PROCESS_INFORMATION)]
kernel32.CreateProcessW.restype = wt.BOOL
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
kernel32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
kernel32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
kernel32.CloseHandle.argtypes = [wt.HANDLE]


def _fail(what):
    raise OSError(f"{what} 실패 (GetLastError={ctypes.get_last_error()})")


def _env_block(env):
    # 윈도우는 환경 블록이 정렬돼 있기를 요구한다
    items = sorted((f"{k}={v}" for k, v in env.items()), key=lambda s: s.upper())
    return ctypes.create_unicode_buffer("\0".join(items) + "\0\0")


class ConPty:
    def __init__(self, cmdline, cwd, env, cols, rows):
        in_read, in_write = wt.HANDLE(), wt.HANDLE()
        out_read, out_write = wt.HANDLE(), wt.HANDLE()
        if not kernel32.CreatePipe(ctypes.byref(in_read), ctypes.byref(in_write), None, 0):
            _fail("CreatePipe(입력)")
        if not kernel32.CreatePipe(ctypes.byref(out_read), ctypes.byref(out_write), None, 0):
            _fail("CreatePipe(출력)")

        self.hpc = HPCON()
        hr = kernel32.CreatePseudoConsole(COORD(max(2, cols), max(1, rows)),
                                          in_read, out_write, 0, ctypes.byref(self.hpc))
        if hr != 0:
            raise OSError(f"CreatePseudoConsole 실패 (HRESULT=0x{hr & 0xFFFFFFFF:08X})")

        # 속성 목록에 의사 콘솔을 달아 CreateProcess 에 넘긴다
        size = ctypes.c_size_t(0)
        kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        attr_buf = ctypes.create_string_buffer(size.value)
        if not kernel32.InitializeProcThreadAttributeList(attr_buf, 1, 0, ctypes.byref(size)):
            _fail("InitializeProcThreadAttributeList")
        if not kernel32.UpdateProcThreadAttribute(attr_buf, 0, ctypes.c_void_p(PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE),
                                                  self.hpc, ctypes.sizeof(HPCON), None, None):
            _fail("UpdateProcThreadAttribute")

        si = STARTUPINFOEXW()
        si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        si.lpAttributeList = ctypes.cast(attr_buf, ctypes.c_void_p)
        self.pi = PROCESS_INFORMATION()

        ok = kernel32.CreateProcessW(
            None, ctypes.create_unicode_buffer(cmdline), None, None, False,
            EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
            ctypes.cast(_env_block(env), ctypes.c_void_p), cwd,
            ctypes.byref(si), ctypes.byref(self.pi))
        kernel32.DeleteProcThreadAttributeList(attr_buf)
        if not ok:
            kernel32.ClosePseudoConsole(self.hpc)
            _fail(f"CreateProcess({cmdline})")

        # 의사 콘솔이 넘겨받은 쪽은 부모가 닫아야 EOF 가 제대로 전달된다
        kernel32.CloseHandle(in_read)
        kernel32.CloseHandle(out_write)

        self._read_fd = msvcrt.open_osfhandle(out_read.value, os.O_RDONLY)
        self._write_fd = msvcrt.open_osfhandle(in_write.value, 0)
        self._closed = False

    def read(self, n=65536) -> bytes:
        try:
            return os.read(self._read_fd, n)
        except OSError:
            return b""

    def write(self, data: bytes):
        try:
            os.write(self._write_fd, data)
        except OSError:
            pass

    def resize(self, cols, rows):
        try:
            kernel32.ResizePseudoConsole(self.hpc, COORD(max(2, cols), max(1, rows)))
        except OSError:
            pass

    def kill(self):
        if self._closed:
            return
        self._closed = True
        try:
            os.close(self._write_fd)
        except OSError:
            pass
        kernel32.ClosePseudoConsole(self.hpc)          # 붙어 있는 셸에게 종료를 알린다
        if kernel32.WaitForSingleObject(self.pi.hProcess, 1500) != 0:
            kernel32.TerminateProcess(self.pi.hProcess, 1)

    def wait(self) -> int:
        kernel32.WaitForSingleObject(self.pi.hProcess, INFINITE)
        code = wt.DWORD(0)
        kernel32.GetExitCodeProcess(self.pi.hProcess, ctypes.byref(code))
        if not self._closed:
            self._closed = True
            try:
                kernel32.ClosePseudoConsole(self.hpc)
            except OSError:
                pass
        for h in (self.pi.hThread, self.pi.hProcess):
            kernel32.CloseHandle(h)
        try:
            os.close(self._read_fd)
        except OSError:
            pass
        return int(code.value)
