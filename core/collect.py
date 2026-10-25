import os
import platform
import socket
import time

import psutil
import requests


def public_ip():
    try:
        return requests.get('https://api.ipify.org', timeout=4).text.strip()
    except Exception:
        return 'n/a'


def gather():
    a, b = [], []
    try:
        a.append(('Host', socket.gethostname()))
    except Exception:
        a.append(('Host', '?'))
    a.append(('User', os.environ.get('USERNAME', '?')))
    a.append(('OS', f'{platform.system()} {platform.release()} {platform.machine()}'))
    a.append(('CPU', f'{platform.processor()} x{psutil.cpu_count()}'))
    vm = psutil.virtual_memory()
    a.append(('RAM', f'{vm.used / 2 ** 30:.1f} / {vm.total / 2 ** 30:.1f} GB'))
    a.append(('Uptime', f'{time.time() - psutil.boot_time():.0f}s'))
    a.append(('Public IP', public_ip()))
    a.append(('TZ', time.tzname[0]))

    ips, macs = [], []
    for name, addrs in psutil.net_if_addrs().items():
        for ad in addrs:
            if ad.family == socket.AF_INET and not ad.address.startswith('127.'):
                ips.append(f'{name}: {ad.address}')
            if ad.family == psutil.AF_LINK and ad.address and ad.address != '00:00:00:00:00:00':
                macs.append(ad.address)
    a.append(('Local IPs', ', '.join(ips[:6]) or 'none'))
    a.append(('MACs', ', '.join(macs[:4]) or 'none'))

    for d in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(d.mountpoint)
            b.append(f'{d.mountpoint} {u.free / 2 ** 30:.1f}GB free / {u.total / 2 ** 30:.1f}GB')
        except Exception:
            pass

    procs = []
    for p in psutil.process_iter(['name', 'pid', 'memory_info']):
        try:
            procs.append((p.info['name'], p.info['pid'], p.info['memory_info'].rss))
        except Exception:
            pass
    procs.sort(key=lambda x: x[2], reverse=True)
    return a, b, [f'{n} [{i}]' for n, i, _ in procs[:15]]