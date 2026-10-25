import asyncio
import hashlib
import io
import os
import pathlib
import shutil

import discord
from discord.ext import commands

from core import web
from core.util import LIMIT, code, human, run, run_ps, say, split_file, tmp, zip_path


class Files(commands.Cog):
    """File manager over Discord."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['dir'])
    async def ls(self, ctx, *, path: str = '.'):
        p = pathlib.Path(path)
        rows = []
        for i in list(p.iterdir())[:200]:
            try:
                rows.append(f'{"d" if i.is_dir() else "-"} {human(i.stat().st_size):>10} {i.name}')
            except Exception:
                rows.append(f'? ? {i.name}')
        await code(ctx.channel, '\n'.join(rows) or '(empty)')

    @commands.command()
    async def tree(self, ctx, *, path: str = '.'):
        await code(ctx.channel, await asyncio.to_thread(run, f'tree /F /A "{path}"', None, 60))

    @commands.command()
    async def dl(self, ctx, *, path: str):
        p = pathlib.Path(path)
        if not p.exists():
            return await say(ctx.channel, 'not found')
        target = str(p)
        if p.is_dir() or p.stat().st_size > LIMIT:
            target = await asyncio.to_thread(zip_path, str(p), tmp('.zip'))
        data = pathlib.Path(target).read_bytes()
        if len(data) <= LIMIT:
            name = p.name if not p.is_dir() else p.name + '.zip'
            await ctx.channel.send(file=discord.File(io.BytesIO(data), name))
        else:
            for name, part in split_file(target, p.name):
                await ctx.channel.send(content=name, file=discord.File(io.BytesIO(part), name))
        if target != str(p):
            os.unlink(target)

    @commands.command()
    async def ul(self, ctx, *, dest: str = '.'):
        d = pathlib.Path(dest)
        d.mkdir(parents=True, exist_ok=True)
        n = 0
        for a in ctx.message.attachments:
            (d / a.filename).write_bytes(await a.read())
            n += 1
        await say(ctx.channel, f'saved {n} → `{d}`')

    @commands.command()
    async def cat(self, ctx, *, path: str):
        await code(ctx.channel, pathlib.Path(path).read_bytes()[:8000].decode('utf-8', 'replace'))

    @commands.command()
    async def rm(self, ctx, *, path: str):
        p = pathlib.Path(path)
        shutil.rmtree(p) if p.is_dir() else p.unlink()
        await say(ctx.channel, 'deleted')

    @commands.command()
    async def mkdir(self, ctx, *, path: str):
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)
        await say(ctx.channel, 'created')

    @commands.command()
    async def mv(self, ctx, src: str, dst: str):
        shutil.move(src, dst)
        await say(ctx.channel, 'moved')

    @commands.command()
    async def cp(self, ctx, src: str, dst: str):
        shutil.copy2(src, dst)
        await say(ctx.channel, 'copied')

    @commands.command()
    async def search(self, ctx, *, pattern: str):
        await code(ctx.channel, await asyncio.to_thread(
            run, f'where /r "%USERPROFILE%" *{pattern}* 2>nul', None, 90))

    @commands.command()
    async def hash(self, ctx, *, path: str):
        await say(ctx.channel, f'`{hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()}`')

    @commands.command()
    async def recent(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps,
            'Get-ChildItem "$env:USERPROFILE" -Recurse -File -EA 0|Sort LastWriteTime -Desc|'
            'Select -First 40 FullName,LastWriteTime|ft -AutoSize|Out-String -Width 200'))

    @commands.command()
    async def drives(self, ctx):
        import psutil
        rows = []
        for d in psutil.disk_partitions():
            try:
                u = psutil.disk_usage(d.mountpoint)
                rows.append(f'{d.device} {d.fstype} {human(u.free)} free / {human(u.total)}')
            except Exception:
                pass
        await code(ctx.channel, '\n'.join(rows))

    @commands.command()
    async def hidden(self, ctx, *, path: str = '.'):
        await code(ctx.channel, await asyncio.to_thread(run, f'dir /a:h "{path}"'))

    @commands.command()
    async def attrs(self, ctx, flag: str, *, path: str):
        await code(ctx.channel, await asyncio.to_thread(run, f'attrib {flag} "{path}"'))

    @commands.command()
    async def shred(self, ctx, *, path: str):
        p = pathlib.Path(path)
        size = p.stat().st_size
        with p.open('r+b') as f:
            f.write(os.urandom(size))
        p.unlink()
        await say(ctx.channel, 'shredded')

    @commands.command()
    async def browse(self, ctx):
        if not web.running():
            return await say(ctx.channel, 'run `!panel` first')
        await say(ctx.channel, f'{web.URL}/?k={self.bot.cfg["web_token"]}#files')


async def setup(bot):
    await bot.add_cog(Files(bot))