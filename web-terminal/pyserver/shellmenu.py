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
        ole32.CLSIDFromString(wt.LPCWSTR(text), ctypes.byref(self))


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
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long,
                             wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


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


def _ensure_class():
    global _class_registered
    if _class_registered:
        return
    class WNDCLASS(ctypes.Structure):
        _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HANDLE),
                    ("hCursor", wt.HANDLE), ("hbrBackground", wt.HANDLE),
                    ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]
    wc = WNDCLASS()
    wc.lpfnWndProc = _wndproc
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = _CLASS_NAME
    user32.RegisterClassW(ctypes.byref(wc))
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
        if not hwnd:
            raise OSError("메뉴를 걸 창을 만들지 못했습니다")
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
            info = CMINVOKECOMMANDINFOEX()
            info.cbSize = ctypes.sizeof(CMINVOKECOMMANDINFOEX)
            info.fMask = 0x00004000 | 0x00000004      # UNICODE | PTINVOKE 없이 단순 호출
            info.hwnd = hwnd
            info.lpVerb = ctypes.c_char_p(cmd - ID_FIRST)
            info.lpVerbW = ctypes.cast(ctypes.c_void_p(cmd - ID_FIRST), wt.LPCWSTR)
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
        if hwnd:
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
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    print(f"'{target}' 의 셸 메뉴를 커서 위치({pt.x}, {pt.y})에 띄웁니다...")
    try:
        _show(target, pt.x, pt.y)
        print("메뉴가 닫혔습니다. (항목을 골랐다면 그 동작이 실행됩니다)")
    except Exception as e:
        import traceback
        print("실패:", e)
        traceback.print_exc()
