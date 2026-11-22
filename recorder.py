"""
Gravador / reprodutor de rotas (teclado + mouse) via Raw Input do Windows.

- Grava teclas por scancode (o que o jogo le) e o mouse em modo relativo
  (camera, quando o cursor esta escondido) ou absoluto (menus, cursor visivel).
- Reproduz com SendInput no mesmo ritmo da gravacao.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import threading
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
winmm = ctypes.WinDLL("winmm")

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

WM_INPUT, WM_DESTROY, WM_STOP = 0x00FF, 0x0002, 0x0400 + 77
RID_INPUT, RIM_TYPEMOUSE, RIM_TYPEKEYBOARD = 0x10000003, 0, 1
RIDEV_INPUTSINK, RIDEV_REMOVE = 0x00000100, 0x00000001
MOUSE_MOVE_ABSOLUTE = 0x01


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HICON), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wt.USHORT), ("usUsage", wt.USHORT),
                ("dwFlags", wt.DWORD), ("hwndTarget", wt.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wt.DWORD), ("dwSize", wt.DWORD),
                ("hDevice", wt.HANDLE), ("wParam", wt.WPARAM)]


class _RMB(ctypes.Structure):
    _fields_ = [("usButtonFlags", wt.USHORT), ("usButtonData", wt.USHORT)]


class _RMU(ctypes.Union):
    _fields_ = [("ulButtons", wt.ULONG), ("s", _RMB)]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", wt.USHORT), ("u", _RMU), ("ulRawButtons", wt.ULONG),
                ("lLastX", wt.LONG), ("lLastY", wt.LONG), ("ulExtraInformation", wt.ULONG)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("MakeCode", wt.USHORT), ("Flags", wt.USHORT), ("Reserved", wt.USHORT),
                ("VKey", wt.USHORT), ("Message", wt.UINT), ("ExtraInformation", wt.ULONG)]


class _RID(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE), ("keyboard", RAWKEYBOARD)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("data", _RID)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD),
                ("hCursor", wt.HICON), ("ptScreenPos", wt.POINT)]


# SendInput
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _IU(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _IU)]


user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wt.ATOM
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
user32.CreateWindowExW.restype = wt.HWND
user32.DestroyWindow.argtypes = [wt.HWND]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.GetRawInputData.argtypes = [wt.HANDLE, wt.UINT, wt.LPVOID, ctypes.POINTER(wt.UINT), wt.UINT]
user32.GetRawInputData.restype = wt.UINT
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wt.UINT, wt.UINT]
user32.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
user32.SendInput.argtypes = [wt.UINT, ctypes.c_void_p, ctypes.c_int]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE

CLASS_NAME = "AutoMacroRawRecorder"
_active = None          # gravador ativo (usado pelo wndproc)
_class_ok = False


def cursor_state():
    ci = CURSORINFO(cbSize=ctypes.sizeof(CURSORINFO))
    user32.GetCursorInfo(ctypes.byref(ci))
    return (1 if ci.flags & 1 else 0), ci.ptScreenPos.x, ci.ptScreenPos.y


def _unregister():
    devs = (RAWINPUTDEVICE * 2)(RAWINPUTDEVICE(1, 2, RIDEV_REMOVE, None),
                                RAWINPUTDEVICE(1, 6, RIDEV_REMOVE, None))
    user32.RegisterRawInputDevices(devs, 2, ctypes.sizeof(RAWINPUTDEVICE))


@WNDPROC
def _wndproc(hwnd, msg, wp, lp):
    r = _active
    if msg == WM_INPUT and r is not None and r.recording:
        try:
            r._on_input(lp)
        except Exception:
            pass
    elif msg == WM_STOP:
        _unregister()
        user32.DestroyWindow(hwnd)
        return 0
    elif msg == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wp, lp)


BUTTON_FLAGS = {0x0001: ("L", 1), 0x0002: ("L", 0), 0x0004: ("R", 1),
                0x0008: ("R", 0), 0x0010: ("M", 1), 0x0020: ("M", 0)}


class Recorder:
    """Formato dos eventos:
       ["k", t, scancode, e0, down]
       ["m", t, dx, dy, cursor_visivel, x, y]
       ["b", t, botao, down, cursor_visivel, x, y]
       ["w", t, delta]"""

    def __init__(self, ignore_vks=()):
        self.ignore = set(ignore_vks)
        self.events = []
        self.recording = False
        self.error = None
        self._hwnd = None
        self._thread = None
        self._keys = set()
        self._btns = set()
        self.t0 = 0.0

    def elapsed(self):
        return time.perf_counter() - self.t0 if self.recording else 0.0

    def start(self):
        if self.recording:
            return
        self.events, self._keys, self._btns, self.error = [], set(), set(), None
        self.t0 = time.perf_counter()
        self.recording = True
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait(2)

    def stop(self):
        if not self.recording:
            return []
        self.recording = False
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_STOP, 0, 0)
        if self._thread:
            self._thread.join(2)
        t = time.perf_counter() - self.t0
        for sc, e0 in list(self._keys):
            self.events.append(["k", t, sc, e0, 0])
        for b in list(self._btns):
            self.events.append(["b", t, b, 0, 0, 0, 0])
        return _trim(self.events)

    def _run(self, ready):
        global _active, _class_ok
        _active = self
        hinst = kernel32.GetModuleHandleW(None)
        if not _class_ok:
            wc = WNDCLASSW(lpfnWndProc=_wndproc, hInstance=hinst, lpszClassName=CLASS_NAME)
            user32.RegisterClassW(ctypes.byref(wc))
            _class_ok = True
        hwnd = user32.CreateWindowExW(0, CLASS_NAME, "rec", 0, 0, 0, 0, 0, None, None, hinst, None)
        self._hwnd = hwnd
        devs = (RAWINPUTDEVICE * 2)(RAWINPUTDEVICE(1, 2, RIDEV_INPUTSINK, hwnd),
                                    RAWINPUTDEVICE(1, 6, RIDEV_INPUTSINK, hwnd))
        if not hwnd or not user32.RegisterRawInputDevices(devs, 2, ctypes.sizeof(RAWINPUTDEVICE)):
            self.error = ctypes.get_last_error()
        ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        self._hwnd = None

    def _on_input(self, lp):
        hdr = ctypes.sizeof(RAWINPUTHEADER)
        size = wt.UINT(0)
        user32.GetRawInputData(lp, RID_INPUT, None, ctypes.byref(size), hdr)
        buf = ctypes.create_string_buffer(max(size.value, ctypes.sizeof(RAWINPUT)))
        if user32.GetRawInputData(lp, RID_INPUT, buf, ctypes.byref(size), hdr) == 0xFFFFFFFF:
            return
        ri = RAWINPUT.from_buffer(buf)
        t = time.perf_counter() - self.t0
        ev = self.events

        if ri.header.dwType == RIM_TYPEKEYBOARD:
            kb = ri.data.keyboard
            if kb.VKey in self.ignore or kb.MakeCode == 0 or kb.Flags & 4:
                return
            e0 = 1 if kb.Flags & 2 else 0
            if kb.MakeCode == 0x2A and e0:      # "shift falso" do Windows
                return
            key, down = (kb.MakeCode, e0), not (kb.Flags & 1)
            if down:
                if key in self._keys:           # auto-repeat de tecla segurada
                    return
                self._keys.add(key)
            else:
                if key not in self._keys:
                    return
                self._keys.discard(key)
            ev.append(["k", t, kb.MakeCode, e0, int(down)])

        elif ri.header.dwType == RIM_TYPEMOUSE:
            m = ri.data.mouse
            show, x, y = cursor_state()
            dx, dy = m.lLastX, m.lLastY
            if (dx or dy) and not (m.usFlags & MOUSE_MOVE_ABSOLUTE):
                last = ev[-1] if ev else None
                if last and last[0] == "m" and t - last[1] < 0.012 and last[4] == show:
                    last[2] += dx; last[3] += dy; last[5], last[6] = x, y
                else:
                    ev.append(["m", t, dx, dy, show, x, y])
            bf = m.u.s.usButtonFlags
            for flag, (b, d) in BUTTON_FLAGS.items():
                if bf & flag:
                    (self._btns.add if d else self._btns.discard)(b)
                    ev.append(["b", t, b, d, show, x, y])
            if bf & 0x0400:
                ev.append(["w", t, ctypes.c_short(m.u.s.usButtonData).value])


def _trim(events):
    if not events:
        return []
    shift = max(0.0, events[0][1] - 0.2)
    for e in events:
        e[1] = round(e[1] - shift, 4)
    return events


# ----------------------------------------------------------------- reproducao
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x8
MOVE, WHEEL = 0x0001, 0x0800
BTN = {("L", 1): 0x0002, ("L", 0): 0x0004, ("R", 1): 0x0008,
       ("R", 0): 0x0010, ("M", 1): 0x0020, ("M", 0): 0x0040}


def _send(inp):
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _key(sc, e0, down):
    i = INPUT(type=1)
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if e0 else 0) | (0 if down else KEYEVENTF_KEYUP)
    i.u.ki = KEYBDINPUT(0, sc, flags, 0, 0)
    _send(i)


def _mouse(flags, dx=0, dy=0, data=0):
    i = INPUT(type=0)
    i.u.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
    _send(i)


def _release(keys, btns):
    for sc, e0 in list(keys):
        _key(sc, e0, False)
    for b in list(btns):
        _mouse(BTN[(b, 0)])


def _press(keys, btns):
    for sc, e0 in list(keys):
        _key(sc, e0, True)
    for b in list(btns):
        _mouse(BTN[(b, 1)])


def play(events, should_run, focused=lambda: True):
    """Reproduz a rota. Pausa sozinho se a janela do jogo perder o foco.
    Retorna True se terminou, False se foi interrompida."""
    keys, btns = set(), set()
    winmm.timeBeginPeriod(1)
    try:
        start = time.perf_counter()
        for ev in events:
            while True:
                if not should_run():
                    return False
                if not focused():
                    _release(keys, btns)
                    paused = time.perf_counter()
                    while not focused():
                        if not should_run():
                            return False
                        time.sleep(0.1)
                    _press(keys, btns)
                    start += time.perf_counter() - paused
                rem = start + ev[1] - time.perf_counter()
                if rem <= 0:
                    break
                time.sleep(min(rem - 0.001, 0.05)) if rem > 0.002 else None

            kind = ev[0]
            if kind == "k":
                _, _, sc, e0, down = ev
                _key(sc, e0, bool(down))
                (keys.add if down else keys.discard)((sc, e0))
            elif kind == "m":
                _, _, dx, dy, show, x, y = ev
                if show:
                    user32.SetCursorPos(x, y)
                else:
                    _mouse(MOVE, dx, dy)
            elif kind == "b":
                _, _, b, down, show, x, y = ev
                if show and (x or y):
                    user32.SetCursorPos(x, y)
                _mouse(BTN[(b, down)])
                (btns.add if down else btns.discard)(b)
            elif kind == "w":
                _mouse(WHEEL, data=ev[2])
        return True
    finally:
        _release(keys, btns)
        winmm.timeEndPeriod(1)


# ----------------------------------------------------------------- arquivos
ROUTES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rotas")


def _safe(name):
    return re.sub(r"[^\w\- ]", "_", name).strip() or "rota"


def save_route(name, events):
    os.makedirs(ROUTES_DIR, exist_ok=True)
    name = _safe(name)
    with open(os.path.join(ROUTES_DIR, name + ".json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "duration": events[-1][1] if events else 0, "events": events}, f)
    return name


def load_route(name):
    try:
        with open(os.path.join(ROUTES_DIR, _safe(name) + ".json"), "r", encoding="utf-8") as f:
            return json.load(f).get("events", [])
    except Exception:
        return []


def delete_route(name):
    try:
        os.remove(os.path.join(ROUTES_DIR, _safe(name) + ".json"))
    except OSError:
        pass


def list_routes():
    if not os.path.isdir(ROUTES_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(ROUTES_DIR)):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(ROUTES_DIR, fn), "r", encoding="utf-8") as f:
                    d = json.load(f)
                out.append((fn[:-5], float(d.get("duration", 0)), len(d.get("events", []))))
            except Exception:
                pass
    return out
