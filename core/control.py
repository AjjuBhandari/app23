import asyncio

from discord.ext import commands

from core import input as inp
from core.util import run_ps, say


class Control(commands.Cog):
    """Mouse and keyboard."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='m')
    async def _m(self, ctx, x: int, y: int):
        inp.move(x, y)
        await ctx.message.add_reaction('🖱')

    @commands.command()
    async def pos(self, ctx):
        await say(ctx.channel, f'`{inp.pos()}`')

    @commands.command()
    async def click(self, ctx, x: int = None, y: int = None):
        inp.click(x, y)
        await ctx.message.add_reaction('🖱')

    @commands.command()
    async def rclick(self, ctx, x: int = None, y: int = None):
        inp.click(x, y, 'right')
        await ctx.message.add_reaction('🖱')

    @commands.command()
    async def dclick(self, ctx, x: int = None, y: int = None):
        inp.dclick(x, y)
        await ctx.message.add_reaction('🖱')

    @commands.command()
    async def scroll(self, ctx, d: int = 120):
        inp.scroll(d)
        await ctx.message.add_reaction('🖱')

    @commands.command()
    async def drag(self, ctx, x1: int, y1: int, x2: int, y2: int):
        inp.drag(x1, y1, x2, y2)
        await ctx.message.add_reaction('🖱')

    @commands.command()
    async def type(self, ctx, *, text: str):
        inp.type_text(text)
        await ctx.message.add_reaction('⌨')

    @commands.command(name='key')
    async def _key(self, ctx, name: str):
        inp.key(name)
        await ctx.message.add_reaction('⌨')

    @commands.command()
    async def hotkey(self, ctx, *names: str):
        inp.hotkey(*names)
        await ctx.message.add_reaction('⌨')

    @commands.command()
    async def focus(self, ctx, pid: int):
        await asyncio.to_thread(run_ps, f'(New-Object -ComObject WScript.Shell).AppActivate({pid})')
        await say(ctx.channel, 'focused')

    @commands.command()
    async def close(self, ctx, pid: int):
        await asyncio.to_thread(run_ps, f'(Get-Process -Id {pid}).CloseMainWindow()|Out-Null')
        await say(ctx.channel, 'sent')

    @commands.command()
    async def minimize(self, ctx):
        inp.hotkey('alt', 'space')
        await asyncio.sleep(.2)
        inp.key('n')
        await say(ctx.channel, 'ok')

    @commands.command()
    async def showdesk(self, ctx):
        inp.hotkey('win', 'd')
        await say(ctx.channel, 'ok')

    @commands.command()
    async def alttab(self, ctx):
        inp.hotkey('alt', 'tab')
        await say(ctx.channel, 'ok')


async def setup(bot):
    await bot.add_cog(Control(bot))