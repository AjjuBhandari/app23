import asyncio
import json
import os
import pathlib

from core import util, web

STATE = pathlib.Path(os.environ.get('APPDATA', '.')) / '.mshelper_panel.json'

_bot = None
_channel_id = None
_msg_id = None
_last_url = None
_lock = asyncio.Lock()


def bind(bot, channel_id):
    global _bot, _channel_id, _msg_id
    _bot, _channel_id = bot, channel_id
    try:
        _msg_id = json.loads(STATE.read_text()).get('msg')
    except Exception:
        _msg_id = None


def _save():
    try:
        STATE.write_text(json.dumps({'msg': _msg_id}))
    except Exception:
        pass


async def _channel():
    if not _bot or not _channel_id:
        return None
    try:
        return _bot.get_channel(int(_channel_id)) or await _bot.fetch_channel(int(_channel_id))
    except Exception:
        return None


async def _edit_or_send(text, bump=False):
    global _msg_id
    ch = await _channel()
    if not ch:
        return
    if _msg_id and not bump:
        try:
            m = await ch.fetch_message(_msg_id)
            await m.edit(content=text)
            return
        except Exception:
            _msg_id = None
    try:
        m = await ch.send(text)
        _msg_id = m.id
        _save()
        try:
            await m.pin(reason='panel link')
        except Exception:
            pass
    except Exception:
        pass


async def repost(url, reason='panel'):
    global _last_url
    async with _lock:
        changed = url != _last_url
        _last_url = url
        label = '**PANEL**' if reason == 'panel' else '**LIVE SCREEN**'
        await _edit_or_send(f'{util.TAG}{label} {url}', bump=changed)


async def down(reason='tunnel'):
    global _last_url
    async with _lock:
        if _last_url is None:
            return
        _last_url = None
        lan = web.lan_url()
        tail = f' — LAN fallback: {lan}' if lan else ''
        await _edit_or_send(f'{util.TAG}**PANEL DOWN** ({reason}){tail}', bump=True)


async def say(text):
    ch = await _channel()
    if ch:
        try:
            await ch.send(f'{util.TAG}{text}')
        except Exception:
            pass


def _spawn(fn, *a):
    try:
        loop = _bot.loop if _bot else asyncio.get_event_loop()
        loop.create_task(fn(*a))
    except Exception:
        pass


async def ensure_panel(bot, cfg, reason='panel'):
    if web.running():
        return web.URL or web.lan_url()
    if not cfg.get('web_port'):
        return None
    return await web.start(cfg['web_port'], cfg.get('web_token', ''), cfg,
                           on_url=lambda u: _spawn(repost, u, reason),
                           on_down=lambda r: _spawn(down, r))