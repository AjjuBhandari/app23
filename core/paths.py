import os
import pathlib
import sys

FROZEN = getattr(sys, 'frozen', False)
APP = 'MicrosoftHelper'

BASE = pathlib.Path(getattr(sys, '_MEIPASS', pathlib.Path(__file__).resolve().parents[1]))
EXE_DIR = pathlib.Path(sys.executable).resolve().parent if FROZEN else BASE
INSTALL = pathlib.Path(os.environ.get('LOCALAPPDATA', '.')) / 'Microsoft' / APP


def config_path():
    for c in (EXE_DIR / 'config.json', BASE / 'config.json', pathlib.Path.cwd() / 'config.json'):
        if c.exists():
            return c
    raise SystemExit('config.json not found')


def runtime_dir():
    return INSTALL if FROZEN else BASE