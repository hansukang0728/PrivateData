"""Windows 셸 컨텍스트 메뉴를 그대로 띄운다 — TortoiseGit, 7-Zip 같은 셸 확장까지.

탐색기가 보여주는 그 메뉴는 등록된 COM 확장(IContextMenu)들이 항목을 채워 넣은
결과다. 흉내낼 방법이 없어서 실제 인터페이스를 ctypes 로 직접 부른다.

    SHParseDisplayName → SHBindToParent → IShellFolder::GetUIObjectOf(IContextMenu)
    → QueryContextMenu → TrackPopupMenuEx → InvokeCommand

혼자 시험해 보려면:  py -3 pyserver\\shellmenu.py "C:\\경로"
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading

if sys.platform != "win32":
    raise ImportError("Windows 전용입니다")

ole32 = ctypes.WinDLL("ole32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# 고해상도 화면에서 좌표가 어긋나지 않도록
try:
    ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)      # PER_MONITOR_DPI_AWARE
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_byte * 8)]

    def __init__(self, text):
        super().__init__()
        ole32.CLSIDFromString(text, ctypes.byref(self))


LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
LPVOID = ctypes.c_void_p

# 반환형을 선언하지 않으면 ctypes 가 32비트 int 로 받아 64비트 핸들이 잘린다.
# 이 선언이 빠지면 CreateWindowExW 가 0 을 돌려주고 메뉴를 띄울 수 없다.
ole32.CLSIDFromString.argtypes = [wt.LPCWSTR, ctypes.POINTER(GUID)]
ole32.CLSIDFromString.restype = ctypes.c_long
ole32.CoInitializeEx.argtypes = [LPVOID, wt.DWORD]
ole32.CoInitializeEx.restype = ctypes.c_long
ole32.CoTaskMemFree.argtypes = [LPVOID]
ole32.CoTaskMemFree.restype = None

shell32.SHParseDisplayName.argtypes = [wt.LPCWSTR, LPVOID, ctypes.POINTER(LPVOID), wt.ULONG, ctypes.POINTER(wt.ULONG)]
shell32.SHParseDisplayName.restype = ctypes.c_long
shell32.SHBindToParent.argtypes = [LPVOID, ctypes.POINTER(GUID), ctypes.POINTER(LPVOID), ctypes.POINTER(LPVOID)]
shell32.SHBindToParent.restype = ctypes.c_long

kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE

user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wt.HWND, wt.HMENU, wt.HINSTANCE, LPVOID]
user32.CreateWindowExW.restype = wt.HWND
user32.DestroyWindow.argtypes = [wt.HWND]
user32.DestroyWindow.restype = wt.BOOL
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.ShowWindow.restype = wt.BOOL
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.SetForegroundWindow.restype = wt.BOOL
user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = wt.HMENU
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.DestroyMenu.restype = wt.BOOL
user32.TrackPopupMenuEx.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, wt.HWND, LPVOID]
user32.TrackPopupMenuEx.restype = ctypes.c_int
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostMessageW.restype = wt.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.GetCursorPos.restype = wt.BOOL
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wt.HWND


IID_IShellFolder = GUID("{000214E6-0000-0000-C000-000000000046}")
IID_IContextMenu = GUID("{000214E4-0000-0000-C000-000000000046}")
IID_IContextMenu2 = GUID("{000214F4-0000-0000-C000-000000000046}")
IID_IContextMenu3 = GUID("{BCFCE0A0-EC17-11D0-8D10-00A0C90F2719}")

COINIT_APARTMENTTHREADED = 0x2
CMF_NORMAL, CMF_EXPLORE, CMF_EXTENDEDVERBS = 0x0, 0x4, 0x100
TPM_RETURNCMD, TPM_RIGHTBUTTON, TPM_LEFTALIGN = 0x0100, 0x0002, 0x0000
ID_FIRST, ID_LAST = 1, 0x7FFF
WS_POPUP, WS_EX_TOOLWINDOW, WS_EX_TOPMOST = 0x80000000, 0x00000080, 0x00000008
SW_SHOWNA = 8
WM_INITMENUPOPUP, WM_DRAWITEM, WM_MEASUREITEM, WM_MENUCHAR, WM_MENUSELECT = 0x0117, 0x002B, 0x002C, 0x0120, 0x011F


def _vcall(ptr, index, restype, *argtypes):
    """COM 인터페이스 포인터의 vtable 에서 index 번째 함수를 꺼낸다."""
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0]
    addr = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))[index]
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(addr)


def _release(ptr):
    if ptr:
        try:
            _vcall(ptr, 2, ctypes.c_ulong)(ptr)
        except Exception:
            pass


def _query(ptr, iid):
    out = ctypes.c_void_p()
    hr = _vcall(ptr, 0, ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
        ptr, ctypes.byref(iid), ctypes.byref(out))
    return out if hr == 0 and out else None


class CMINVOKECOMMANDINFOEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD), ("fMask", wt.DWORD), ("hwnd", wt.HWND),
        ("lpVerb", ctypes.c_char_p), ("lpParameters", ctypes.c_char_p),
        ("lpDirectory", ctypes.c_char_p), ("nShow", ctypes.c_int),
        ("dwHotKey", wt.DWORD), ("hIcon", wt.HANDLE),
        ("lpTitle", ctypes.c_char_p), ("lpVerbW", wt.LPCWSTR),
        ("lpParametersW", wt.LPCWSTR), ("lpDirectoryW", wt.LPCWSTR),
        ("lpTitleW", wt.LPCWSTR), ("ptInvoke", wt.POINT),
    ]


# 셸 확장이 그리는 메뉴(아이콘·하위 메뉴)는 창 프로시저가 메시지를 넘겨줘야 채워진다
_ctx2 = ctypes.c_void_p()
_ctx3 = ctypes.c_void_p()
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


@WNDPROC
def _wndproc(hwnd, msg, wparam, lparam):
    if msg in (WM_INITMENUPOPUP, WM_DRAWITEM, WM_MEASUREITEM, WM_MENUCHAR, WM_MENUSELECT):
        if _ctx3:
            res = ctypes.c_void_p()
            hr = _vcall(_ctx3, 7, ctypes.c_long, wt.UINT, wt.WPARAM, wt.LPARAM, ctypes.POINTER(ctypes.c_void_p))(
                _ctx3, msg, wparam, lparam, ctypes.byref(res))
            if hr == 0:
                return res.value or 0
        if _ctx2:
            _vcall(_ctx2, 6, ctypes.c_long, wt.UINT, wt.WPARAM, wt.LPARAM)(_ctx2, msg, wparam, lparam)
            return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


_class_registered = False
_CLASS_NAME = "PoshDeckShellMenu"
_wndclass = None                    # 등록 후에도 살아 있어야 한다 (GC 방지)


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HANDLE),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HANDLE),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]
user32.RegisterClassW.restype = wt.ATOM


def _ensure_class():
    global _class_registered, _wndclass
    if _class_registered:
        return
    wc = WNDCLASS()
    wc.lpfnWndProc = _wndproc
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = _CLASS_NAME
    atom = user32.RegisterClassW(ctypes.byref(wc))
    err = ctypes.get_last_error()
    if not atom and err != 1410:                       # 1410 = 이미 등록됨
        raise OSError(f"창 클래스를 등록하지 못했습니다 (RegisterClassW, GetLastError={err})")
    _wndclass = wc
    _class_registered = True


def _show(path, x, y, extended=False):
    """이 함수는 사용자가 항목을 고를 때까지 돌아오지 않는다 (메뉴가 모달)."""
    global _ctx2, _ctx3
    ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    pidl = ctypes.c_void_p()
    parent = ctypes.c_void_p()
    child = ctypes.c_void_p()
    menu = None
    hwnd = None
    owned = False
    ctx = ctypes.c_void_p()
    try:
        hr = shell32.SHParseDisplayName(wt.LPCWSTR(path), None, ctypes.byref(pidl), 0, None)
        if hr != 0:
            raise OSError(f"경로를 셸에 전달하지 못했습니다 (SHParseDisplayName 0x{hr & 0xFFFFFFFF:08X}): {path}")

        hr = shell32.SHBindToParent(pidl, ctypes.byref(IID_IShellFolder),
                                    ctypes.byref(parent), ctypes.byref(child))
        if hr != 0 or not parent:
            raise OSError(f"상위 폴더를 얻지 못했습니다 (SHBindToParent 0x{hr & 0xFFFFFFFF:08X})")

        arr = (ctypes.c_void_p * 1)(child)
        hr = _vcall(parent, 10, ctypes.c_long, wt.HWND, wt.UINT, ctypes.c_void_p,
                    ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            parent, None, 1, arr, ctypes.byref(IID_IContextMenu), None, ctypes.byref(ctx))
        if hr != 0 or not ctx:
            raise OSError(f"컨텍스트 메뉴를 얻지 못했습니다 (GetUIObjectOf 0x{hr & 0xFFFFFFFF:08X})")

        _ctx2 = _query(ctx, IID_IContextMenu2) or ctypes.c_void_p()
        _ctx3 = _query(ctx, IID_IContextMenu3) or ctypes.c_void_p()

        _ensure_class()
        hwnd = user32.CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_TOPMOST, _CLASS_NAME, "",
                                      WS_POPUP, int(x), int(y), 1, 1, None, None,
                                      kernel32.GetModuleHandleW(None), None)
        owned = bool(hwnd)
        if not hwnd:
            # 우리 창을 못 만들었으면 앞에 있는 창(대개 브라우저)을 주인으로 쓴다.
            # 셸 확장이 그리는 아이콘·하위 메뉴는 덜 나올 수 있지만 메뉴 자체는 뜬다.
            err = ctypes.get_last_error()
            hwnd = user32.GetForegroundWindow()
            print(f"[PoshDeck] 전용 창 생성 실패(GetLastError={err}) — 앞 창을 주인으로 대신 씁니다")
            if not hwnd:
                raise OSError(f"메뉴를 걸 창을 만들지 못했습니다 (CreateWindowExW, GetLastError={err})")
        else:
            user32.ShowWindow(hwnd, SW_SHOWNA)
            user32.SetForegroundWindow(hwnd)

        menu = user32.CreatePopupMenu()
        flags = CMF_EXPLORE | (CMF_EXTENDEDVERBS if extended else 0)
        hr = _vcall(ctx, 3, ctypes.c_long, wt.HMENU, wt.UINT, wt.UINT, wt.UINT, wt.UINT)(
            ctx, menu, 0, ID_FIRST, ID_LAST, flags)
        if hr < 0:
            raise OSError(f"메뉴를 채우지 못했습니다 (QueryContextMenu 0x{hr & 0xFFFFFFFF:08X})")

        user32.TrackPopupMenuEx.restype = ctypes.c_int
        cmd = user32.TrackPopupMenuEx(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_LEFTALIGN,
                                      int(x), int(y), hwnd, None)
        user32.PostMessageW(hwnd, 0, 0, 0)
        if cmd > 0:
            verb_id = cmd - ID_FIRST                  # MAKEINTRESOURCE — 정수를 포인터 자리에 넣는다
            info = CMINVOKECOMMANDINFOEX()
            info.cbSize = ctypes.sizeof(CMINVOKECOMMANDINFOEX)
            info.fMask = 0x00004000                   # CMIC_MASK_UNICODE
            info.hwnd = hwnd
            info.lpVerb = ctypes.cast(ctypes.c_void_p(verb_id), ctypes.c_char_p)
            info.lpVerbW = ctypes.cast(ctypes.c_void_p(verb_id), wt.LPCWSTR)
            info.nShow = 1                            # SW_SHOWNORMAL
            info.lpDirectory = os.path.dirname(path).encode("mbcs", "replace")
            info.lpDirectoryW = os.path.dirname(path)
            hr = _vcall(ctx, 4, ctypes.c_long, ctypes.c_void_p)(ctx, ctypes.byref(info))
            if hr != 0:
                raise OSError(f"선택한 항목을 실행하지 못했습니다 (InvokeCommand 0x{hr & 0xFFFFFFFF:08X})")
        return True
    finally:
        _ctx2, _ctx3 = ctypes.c_void_p(), ctypes.c_void_p()
        if menu:
            user32.DestroyMenu(menu)
        if hwnd and owned:
            user32.DestroyWindow(hwnd)
        for p in (ctx, parent):
            _release(p)
        if pidl:
            ole32.CoTaskMemFree(pidl)
        ole32.CoUninitialize()


def show_async(path, x, y, extended=False):
    """메뉴는 모달이라 별도 스레드(STA)에서 띄운다. 오류는 큐에 남겨 다음 요청이 가져간다."""
    box = {}

    def run():
        try:
            _show(path, x, y, extended)
        except Exception as e:
            box["error"] = f"{type(e).__name__}: {e}"
            print("[PoshDeck] 셸 메뉴 실패:", box["error"])

    th = threading.Thread(target=run, daemon=True, name="shellmenu")
    th.start()
    th.join(0.8)                                       # 곧바로 실패하는 경우는 알려줄 수 있다
    return box.get("error")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~")
    print("=" * 60)
    print("  PoshDeck 셸 메뉴 진단")
    print("=" * 60)
    print(f"  대상: {target}")
    print(f"  파이썬: {sys.version.split()[0]} ({ctypes.sizeof(ctypes.c_void_p) * 8}비트)")
    print()

    step = "준비"
    try:
        step = "1) COM 초기화"
        ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        print("  [ OK ]", step)

        step = "2) 경로를 셸 항목으로 변환 (SHParseDisplayName)"
        pidl = LPVOID()
        hr = shell32.SHParseDisplayName(target, None, ctypes.byref(pidl), 0, None)
        if hr != 0:
            raise OSError(f"HRESULT 0x{hr & 0xFFFFFFFF:08X}")
        print("  [ OK ]", step)

        step = "3) 상위 폴더 인터페이스 (SHBindToParent)"
        parent, child = LPVOID(), LPVOID()
        hr = shell32.SHBindToParent(pidl, ctypes.byref(IID_IShellFolder), ctypes.byref(parent), ctypes.byref(child))
        if hr != 0 or not parent:
            raise OSError(f"HRESULT 0x{hr & 0xFFFFFFFF:08X}")
        print("  [ OK ]", step)

        step = "4) 컨텍스트 메뉴 인터페이스 (GetUIObjectOf)"
        arr = (LPVOID * 1)(child)
        ctx = LPVOID()
        hr = _vcall(parent, 10, ctypes.c_long, wt.HWND, wt.UINT, LPVOID, LPVOID, LPVOID, ctypes.POINTER(LPVOID))(
            parent, None, 1, arr, ctypes.byref(IID_IContextMenu), None, ctypes.byref(ctx))
        if hr != 0 or not ctx:
            raise OSError(f"HRESULT 0x{hr & 0xFFFFFFFF:08X}")
        print("  [ OK ]", step)
        print("        IContextMenu2:", "있음" if _query(ctx, IID_IContextMenu2) else "없음",
              "· IContextMenu3:", "있음" if _query(ctx, IID_IContextMenu3) else "없음")

        step = "5) 창 클래스 등록 (RegisterClassW)"
        _ensure_class()
        print("  [ OK ]", step)

        step = "6) 창 생성 (CreateWindowExW)"
        hinst = kernel32.GetModuleHandleW(None)
        print(f"        모듈 핸들: 0x{(hinst or 0):X}")
        hwnd = user32.CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_TOPMOST, _CLASS_NAME, "",
                                      WS_POPUP, 0, 0, 1, 1, None, None, hinst, None)
        if not hwnd:
            raise OSError(f"GetLastError={ctypes.get_last_error()}")
        print(f"  [ OK ] {step} — 핸들 0x{hwnd:X}")
        user32.DestroyWindow(hwnd)

        step = "7) 메뉴 채우기 (QueryContextMenu)"
        menu = user32.CreatePopupMenu()
        hr = _vcall(ctx, 3, ctypes.c_long, wt.HMENU, wt.UINT, wt.UINT, wt.UINT, wt.UINT)(
            ctx, menu, 0, ID_FIRST, ID_LAST, CMF_EXPLORE)
        if hr < 0:
            raise OSError(f"HRESULT 0x{hr & 0xFFFFFFFF:08X}")
        user32.GetMenuItemCount.argtypes = [wt.HMENU]
        user32.GetMenuItemCount.restype = ctypes.c_int
        print(f"  [ OK ] {step} — 항목 {user32.GetMenuItemCount(menu)}개")
        user32.DestroyMenu(menu)

        print()
        print("  준비는 모두 통과했습니다. 실제로 메뉴를 띄웁니다...")
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        _show(target, pt.x, pt.y)
        print("  메뉴가 닫혔습니다. (항목을 골랐다면 그 동작이 실행됩니다)")
        print()
        print("  결과: 정상")
    except Exception as e:
        import traceback
        print(f"  [실패] {step}")
        print(f"         {type(e).__name__}: {e}")
        print()
        traceback.print_exc()
        print()
        print("  이 화면을 그대로 복사해서 알려주시면 바로 잡겠습니다.")
    print("=" * 60)
    input("\n엔터를 누르면 닫힙니다...")
