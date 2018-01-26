import asyncio, logging

import discord

import plugins

CLIENT = discord.Client()
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

async def send_message_invariant(source, source_id, message):
    """Sends a message to either discord or hangouts"""
    LOGGER.info("Sending message to %s conversation %s: %s", source, source_id, message)
    if source == "discord":
        await CLIENT.send_message(CLIENT.get_channel(source_id), message)
    elif source == "hangouts":
        await CLIENT.hangouts_bot.coro_send_message(source_id, message)

async def do_help(source, source_id):
    """Send a list of commands back to the sender"""
    help_message = "!addrelay <other_id>, !delrelay <other_id>, !getid, !help"
    await send_message_invariant(source, source_id, help_message)

async def do_getid(source, source_id):
    """Send this conversation's id back to the sender"""
    await send_message_invariant(source, source_id, "this conversation's id: {}".format(source_id))

async def do_addrelay(source, source_id, **args):
    """Add a relay from this conversation to the opposite type of conversation"""
    target = "discord" if source == "hangouts" else "hangouts"
    # error: didn't specify target id
    if "arg_string" not in args:
        await send_message_invariant(source, source_id, "usage: !addrelay <{}_id>".format(target))
        return
    arg_string = args["arg_string"]
    target_id = arg_string.split(" ", 1)[0]
    LOGGER.info("relay add request received from %s channel %s to %s channel %s",
                source,
                source_id,
                target,
                target_id)
    relay_map = CLIENT.hangouts_bot.memory.get_by_path(["discord_relay_map"])
    if source_id not in relay_map[source]:
        relay_map[source][source_id] = {}
    if target_id not in relay_map[target]:
        relay_map[target][target_id] = {}
    relay_map[source][source_id][target_id] = True
    relay_map[target][target_id][source_id] = True
    CLIENT.hangouts_bot.memory.set_by_path(["discord_relay_map"], relay_map)
    CLIENT.relay_map = relay_map

async def do_delrelay(source, source_id, **args):
    """Delete a relay"""
    target = "discord" if source == "hangouts" else "hangouts"
    if "arg_string" not in args:
        await send_message_invariant(source, source_id, "usage: !delrelay <{}_id>".format(target))
    arg_string = args["arg_string"]
    target_id = arg_string.split(" ", 1)[0]
    LOGGER.info("relay delete request received from %s channel %s to %s channel %s",
                source,
                source_id,
                target,
                target_id)
    relay_map = CLIENT.hangouts_bot.memory.get_by_path(["discord_relay_map"])
    if source_id not in relay_map[source]:
        await send_message_invariant(source, source_id, "no relays found for this channel")
        return
    if target_id not in relay_map[target]:
        await send_message_invariant(source, source_id, "there are no relays to that channel")
        return
    if target_id not in relay_map[source][source_id] or source_id not in relay_map[target][target_id]:
        msg = "there is no relay between this channel and {} channel {}".format(target, target_id)
        await send_message_invariant(source, source_id, msg)
        return
    del relay_map[source][source_id][target_id]
    del relay_map[target][target_id][source_id]
    CLIENT.hangouts_bot.memory.set_by_path(["discord_relay_map"], relay_map)
    CLIENT.relay_map = relay_map

async def do_relaydump(source, source_id):
    """Print a list of relay maps"""
    msg = "here is a list of relays"
    await send_message_invariant(source, source_id, msg)
    await send_message_invariant(source, source_id, str(CLIENT.relay_map[source]))

COMMAND_DICT = {
    "!help": do_help,
    "!getid": do_getid,
    "!addrelay": do_addrelay,
    "!delrelay": do_delrelay,
    "!relaydump": do_relaydump
}

def _initialize(bot):
    plugins.register_handler(_received_message, type="message", priority=50)
    CLIENT.hangouts_bot = bot
    _start_discord_account(bot)
    _init_discord_map(bot)

# Called when the bot starts up
# Need to set up the discord connection and account here
def _start_discord_account(bot):
    loop = asyncio.get_event_loop()
    LOGGER.info("start discord account here")
    discord_config = bot.get_config_option('discord')
    token = discord_config['token']
    coro = CLIENT.start(token)
    asyncio.run_coroutine_threadsafe(coro, loop)

def _init_discord_map(bot):
    if not bot.memory.exists(["discord_relay_map"]):
        bot.memory.set_by_path(["discord_relay_map"], {})
    relay_map = bot.memory.get_by_path(["discord_relay_map"])
    if "discord" not in relay_map:
        relay_map["discord"] = {}
    if "hangouts" not in relay_map:
        relay_map["hangouts"] = {}
    bot.memory.set_by_path(["discord_relay_map"], relay_map)
    CLIENT.relay_map = relay_map

@CLIENT.event
async def on_ready():
    """On ready handler"""
    LOGGER.info("Logged in as")
    LOGGER.info(CLIENT.user.name)
    LOGGER.info(CLIENT.user.id)
    LOGGER.info("------")

async def parse_command(source, source_id, content):
    """Parse commands. Supported commands are !getid, !addrelay, !delrelay, !help

    Return True if a command was found"""
    LOGGER.info("content is %s", content)
    tokens = content.split(" ", 1)
    command = tokens[0]
    if command in COMMAND_DICT:
        LOGGER.debug("command is %s", command)
        if len(tokens) == 1:
            await COMMAND_DICT[command](source, source_id)
        else:
            await COMMAND_DICT[command](source, source_id, arg_string=tokens[1])
        return True
    return False

# discord message handler
@CLIENT.event
async def on_message(message):
    """Discord message event handler"""
    if message.author.id == CLIENT.user.id:
        return
    if await parse_command("discord", message.channel.id, message.content):
        return
    content = message.content
    author = str(message.author).rsplit('#', 1)[0]
    new_message = "<b>{}:</b> {}".format(author, content)
    LOGGER.info("message from discord")
    LOGGER.info(new_message)
    for convid in CLIENT.relay_map["discord"][message.channel.id]:
        LOGGER.info("sending to {}".format(convid))
        await CLIENT.hangouts_bot.coro_send_message(convid, new_message)

# hangouts message handler
def _received_message(bot, event, command):
    coro = parse_command("hangouts", event.conv_id, event.text)
    loop = asyncio.get_event_loop()
    if asyncio.run_coroutine_threadsafe(coro, loop):
        return
    new_message = "**{}**: {}".format(event.user.full_name, event.text)
    LOGGER.info("message from hangouts")
    LOGGER.info(new_message)
    # send message to discord here
    for chan in CLIENT.relay_map["hangouts"][event.conv_id]:
        if CLIENT.get_channel(chan).type == discord.ChannelType.text:
            LOGGER.info(chan)
            yield from CLIENT.send_message(chan, new_message)