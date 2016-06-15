# vim: set ts=4 expandtab sw=4

import plugins
from hangups import ChatMessageSegment

import aiohttp
import asyncio
import io
import json
import os.path
import re

_cache = {}

def _initialise():
    plugins.register_user_command(["xkcd"])
    plugins.register_handler(_watch_xkcd_link, type="message")

regexps = (
    "https?://(?:www\.)?(?:explain)?xkcd.com/([0-9]+)(?:/|\s|$)",
    "https?://(?:www\.)?explainxkcd.com/wiki/index\.php(?:/|\?title=)([0-9]+)(?:[^0-9]|$)",
    "(?:\s|^)xkcd\s+(?:#\s*)?([0-9]+)(?:\s|$)",
)

@asyncio.coroutine
def xkcd(bot, event, *args):
    """show latest xkcd comic"""
    
    if args == ("clear", ):
        _cache.clear()
    
    if len(args):
        # will be handled by the message handler
        return
    yield from _print_comic(bot, event)

@asyncio.coroutine
def _watch_xkcd_link(bot, event, command):
    # Don't handle events caused by the bot himself
    if event.user.is_self:
        return
    
    for regexp in regexps:
        match = re.search(regexp, event.text, flags=re.IGNORECASE)
        if not match:
            continue
        
        num = match.group(1)
        yield from _print_comic(bot, event, num)
        return # only one match per message

def _print_comic(bot, event, num=None):
    if num:
        num = int(num)
        url = 'https://xkcd.com/%d/info.0.json' % num
    else:
        num = None
        url = 'https://xkcd.com/info.0.json'
    
    if num in _cache:
        info = _cache[num]
    else:
        request = yield from aiohttp.request('get', url)
        raw = yield from request.read()
        info = json.loads(raw.decode())
        
        if info['num'] in _cache:
            info = _cache[info['num']]
        else:
            filename = os.path.basename(info["img"])
            request = yield from aiohttp.request('get', info["img"])
            raw = yield from request.read()
            image_data = io.BytesIO(raw)
            info['image_id'] = yield from bot._client.upload_image(image_data, filename=filename)
            _cache[info['num']] = info
    
    image_id = info['image_id']
    
    context = {
        "parser": False,
    }
    
    msg1 = [
        ChatMessageSegment("xkcd #%s: " % info['num']),
        ChatMessageSegment(info["title"], is_bold=True),
    ]
    msg2 = [
        ChatMessageSegment(info["alt"]),
    ] + ChatMessageSegment.from_str('<br/>- <i><a href="https://xkcd.com/%s">CC-BY-SA xkcd</a></i>' % info['num'])
    if "link" in info and info["link"]:
        msg2.extend(ChatMessageSegment.from_str("<br/>* see also %s" % info["link"]))
    
    yield from bot.coro_send_message(event.conv.id_, msg1, context)
    yield from bot.coro_send_message(event.conv.id_, msg2, context, image_id=image_id) # image appears above text, so order is [msg1, image, msg2]

