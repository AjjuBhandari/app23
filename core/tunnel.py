import asyncio
import pathlib
import re
import shutil
import subprocess
import time
import urllib.request
import zipfile

from core.paths import BASE

BIN = BASE / 'bin'
NO_WIN = 0x08000000
DEADLINE = 50

PATTERNS = {
    'cloudflare': rb'https://[a-z0-9-]+\.trycloudflare\.com',
    'bore': rb'bore\.pub:\d{4,5}',
    'localhost.run': rb'https://[a-z0-9-]+\.lhr\.life',
    'serveo': rb'https://[a-z0-9-]+\.serveo\.net',
}

ORDER = ['cloudflare', 'bore', 'localhost.run', 'serveo']


# ------------------------------------------------------------------ downloads
def _dl(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    urllib.request.urlretrieve(url, dest)
    return dest


def cloudflared():
    p = BIN / 'cloudflared.exe'
    if p.exists():
        return p
    return _dl('https://github.com/cloudflare/cloudflared/releases/latest/download/'
               'cloudflared-windows-amd64.exe', p)


def bore():
    p = BIN / 'bore.exe'
    if p.exists():
        return p
    z = BIN / 'bore.zip'
    _dl('https://github.com/ekzhang/bore/releases/latest/download/'
        'bore-x86_64-pc-windows-msvc.zip', z)
    with zipfile.ZipFile(z) as f:
        for n in f.namelist():
            if n.endswith('.exe'):
                with f.open(n) as src, open(p, 'wb') as dst:
                    dst.write(src.read())
                break
    return p


# ------------------------------------------------------------------ providers
def _spawn(args):
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=NO_WIN)


def _spawn_cloudflare(port):
    exe = cloudflared()
    proto = 'http2' if time.time() % 2 < 1 else 'quic'
    return _spawn([str(exe), 'tunnel', '--no-autoupdate', '--edge-ip-version', '4',
                   '--protocol', proto, '--retries', '5', '--metrics', '127.0.0.1:0',
                   '--url', f'http://127.0.0.1:{port}'])


def _spawn_bore(port):
    return _spawn([str(bore()), 'local', str(port), '--to', 'bore.pub'])


def _spawn_ssh(host, port):
    if not shutil.which('ssh'):
        raise RuntimeError('ssh not found')
    return _spawn(['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ServerAliveInterval=20',
                   '-o', 'ExitOnForwardFailure=yes',
                   '-R', f'80:localhost:{port}', f'nokey@{host}'])


SPAWNERS = {
    'cloudflare': _spawn_cloudflare,
    'bore': lambda port: _spawn_bore(port),
    'localhost.run': lambda port: _spawn_ssh('localhost.run', port),
    'serveo': lambda port: _spawn_ssh('serveo.net', port),
}


def normalise(provider, raw):
    if provider == 'bore':
        return f'http://{raw}'
    return raw


async def _read_until(proc, provider, deadline):
    """Read merged output until the URL pattern shows up."""
    pat = re.compile(PATTERNS[provider])
    end = time.time() + deadline
    while time.time() < end:
        line = await asyncio.to_thread(proc.stdout.readline)
        if not line:
            if proc.poll() is not None:
                return None
            await asyncio.sleep(0.2)
            continue
        m = pat.search(line)
        if m:
            return m.group(0).decode() if isinstance(m.group(0), bytes) else m.group(0)
    return None


class Tunnel:
    """Tries each provider in turn, restarts on death, reports URLs."""

    def __init__(self, port, token, on_url, on_down, order=None):
        self.port = port
        self.token = token
        self.on_url = on_url
        self.on_down = on_down
        self.order = order or ORDER
        self.proc = None
        self.url = None
        self.provider = None
        self.running = False
        self._task = None

    # ---------------------------------------------------------------- loop
    async def _try(self, provider):
        try:
            proc = await asyncio.to_thread(SPAWNERS[provider], self.port)
        except Exception as e:
            return None, f'{provider}: {e}'

        got = await _read_until(proc, provider, DEADLINE)
        if not got:
            try:
                proc.kill()
            except Exception:
                pass
            return None, f'{provider}: no url'

        self.proc = proc
        self.provider = provider
        return normalise(provider, got), None

    async def _loop(self):
        idx = 0
        while self.running:
            provider = self.order[idx % len(self.order)]
            url, err = await self._try(provider)

            if not self.running:
                break

            if url:
                idx = 0
                if url != self.url:
                    self.url = url
                    self._fire(self.on_url, f'{url}/?k={self.token}', provider)
            else:
                idx += 1
                if self.on_down and idx <= len(self.order):
                    self._fire(self.on_down, err or 'failed')

            while self.running and self.proc and self.proc.poll() is None:
                await asyncio.sleep(3)

            if not self.running:
                break

            self.url = None
            self._fire(self.on_down, f'{self.provider} dropped')
            idx += 1
            await asyncio.sleep(min(20, 3 * idx))

    @staticmethod
    def _fire(fn, *a):
        if not fn:
            return
        try:
            fn(*a)
        except Exception:
            pass

    # ---------------------------------------------------------------- api
    async def start(self):
        if self.running:
            return self.url
        self.running = True
        self._task = asyncio.create_task(self._loop())
        for _ in range(DEADLINE + 10):
            if self.url:
                return self.url
            await asyncio.sleep(1)
        return None

    async def stop(self):
        self.running = False
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass
            self.proc = None
        if self._task:
            self._task.cancel()
            self._task = None
        self.url = None
        self.provider = None