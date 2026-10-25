import base64
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
import zipfile

TAG = ''
CWD = {'path': str(pathlib.Path.home())}
LIMIT = 8 * 1024 * 1024
NO_WIN = 0x08000000


def run(cmd, cwd=None, timeout=120):
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd or CWD['path'],
                           capture_output=True, timeout=timeout, creationflags=NO_WIN)
        out = (p.stdout + p.stderr).decode('utf-8', 'replace').strip()
        return out or '(no output)'
    except subprocess.TimeoutExpired:
        return '(timeout)'
    except Exception as e:
        return f'(error) {e}'


def run_ps(script, timeout=60):
    b = base64.b64encode(script.encode('utf-16-le')).decode()
    return run(f'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {b}',
               timeout=timeout)


def human(n):
    for u in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024:
            return f'{n:.1f} {u}'
        n /= 1024
    return f'{n:.1f} PB'


def chunk(s, n=1900):
    return [s[i:i + n] for i in range(0, len(s), n)]


async def say(ch, text):
    return await ch.send((TAG if getattr(ch, 'guild', None) else '') + str(text)[:1990])


async def code(ch, text):
    for p in chunk('```\n' + str(text) + '\n```'):
        await ch.send(p)


def split_file(path, name):
    data = pathlib.Path(path).read_bytes()
    return [(name + f'.{i:03d}', data[i:i + LIMIT]) for i in range(0, len(data), LIMIT)]


def zip_path(src, out):
    if pathlib.Path(src).is_dir():
        shutil.make_archive(out[:-4], 'zip', src)
    else:
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(src, pathlib.Path(src).name)
    return out


def tmp(suffix=''):
    return os.path.join(tempfile.gettempdir(), f'{int(time.time() * 1000)}{suffix}')