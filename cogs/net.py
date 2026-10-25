import asyncio
from discord.ext import commands
from core.util import run, run_ps, say, code


class Net(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def netstat(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run, 'netstat -ano'))

    @commands.command()
    async def arp(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run, 'arp -a'))

    @commands.command()
    async def dns(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run, 'ipconfig /all'))

    @commands.command()
    async def route(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run, 'route print'))

    @commands.command()
    async def fw(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(
            run_ps, 'Get-NetFirewallProfile|Select Name,Enabled|ft -AutoSize|Out-String'))

    @commands.command()
    async def shares(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run, 'net share'))

    @commands.command()
    async def pinghost(self, ctx, host: str):
        await code(ctx.channel, await asyncio.to_thread(run, f'ping -n 4 {host}'))

    @commands.command()
    async def portscan(self, ctx, host: str, start: int = 1, end: int = 1024):
        found = []

        async def chk(p):
            try:
                r, w = await asyncio.wait_for(asyncio.open_connection(host, p), 0.6)
                w.close()
                found.append(p)
            except Exception:
                pass

        for i in range(start, end + 1, 200):
            await asyncio.gather(*[chk(p) for p in range(i, min(i + 200, end + 1))])
        await say(ctx.channel, f'open: {sorted(found) or "none"}')

    @commands.command()
    async def prox(self, ctx):
        await code(ctx.channel, await asyncio.to_thread(run_ps, 'netsh winhttp show proxy'))


async def setup(bot):
    await bot.add_cog(Net(bot))