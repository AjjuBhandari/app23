from pynput.keyboard import Controller as K, Key, KeyCode
from pynput.mouse import Button, Controller as M

mouse, kb = M(), K()


def move(x, y):
    mouse.position = (int(x), int(y))


def pos():
    return mouse.position


def click(x=None, y=None, btn='left'):
    if x is not None:
        move(x, y)
    mouse.click({'left': Button.left, 'right': Button.right, 'middle': Button.middle}[btn])


def dclick(x=None, y=None):
    if x is not None:
        move(x, y)
    mouse.click(Button.left, 2)


def scroll(d):
    mouse.scroll(0, int(d) / 120)


def drag(x1, y1, x2, y2):
    move(x1, y1)
    mouse.press(Button.left)
    move(x2, y2)
    mouse.release(Button.left)


def type_text(t):
    kb.type(t)


KEYS = {'ENTER': Key.enter, 'TAB': Key.tab, 'ESC': Key.esc, 'SPACE': Key.space,
        'BACKSPACE': Key.backspace, 'DELETE': Key.delete, 'UP': Key.up, 'DOWN': Key.down,
        'LEFT': Key.left, 'RIGHT': Key.right, 'HOME': Key.home, 'END': Key.end,
        'PGUP': Key.page_up, 'PGDN': Key.page_down, 'WIN': Key.cmd, 'ALT': Key.alt,
        'CTRL': Key.ctrl, 'SHIFT': Key.shift, 'F1': Key.f1, 'F2': Key.f2, 'F3': Key.f3,
        'F4': Key.f4, 'F5': Key.f5, 'F6': Key.f6, 'F7': Key.f7, 'F8': Key.f8,
        'F9': Key.f9, 'F10': Key.f10, 'F11': Key.f11, 'F12': Key.f12}


def key(name):
    k = KEYS.get(name.upper())
    if k:
        kb.press(k)
        kb.release(k)
    elif len(name) == 1:
        kb.press(name)
        kb.release(name)


def hotkey(*names):
    ks = [KEYS.get(n.upper()) or KeyCode.from_char(n) for n in names]
    for k in ks:
        kb.press(k)
    for k in reversed(ks):
        kb.release(k)