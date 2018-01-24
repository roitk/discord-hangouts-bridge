import asyncio, logging

import discord

import plugins

client = discord.Client()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
bot_global = None

async def send_message_invariant(source, source_id, message):
    """Sends a message to either discord or hangouts"""
    logger.info("in send_message_invariant")
    if source == "discord":
        await client.send_message(client.get_channel(source_id), message)
    elif source == "hangouts":
        await bot_global.coro_send_message(source_id, message)

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
    relay_map = bot_global.memory.get_by_path(["discord_relay_map"])
    target_id = arg_string.split(" ", 1)[0]
    if source_id not in relay_map[source]:
        relay_map[source][source_id] = set()
    if target_id not in relay_map[target]:
        relay_map[target][target_id] = set()
    relay_map[source][source_id].add(target_id)
    relay_map[target][target_id].add(source_id)
    bot_global.memory.set_by_path(["discord_relay_map"], relay_map)

async def do_delrelay(source, source_id, **args):
    target = "discord" if source == "hangouts" else "hangouts"
    if "arg_string" not in args:
        await send_message_invariant(source, source_id, "usage: !delrelay <{}_id>".format(target))
    relay_map = bot_global.memory.get_by_path(["discord_relay_map"])

command_dict = {
    "!help": do_help,
    "!getid": do_getid,
    "!addrelay": do_addrelay,
    "!delrelay": do_delrelay
}

def _initialize(bot):
    plugins.register_handler(_received_message, type="message", priority=50)
    global bot_global
    bot_global = bot
    _start_discord_account(bot)
    _init_discord_map(bot)

def _init_discord_map(bot):
    if not bot.memory.exists(["discord_relay_map"]):
        bot.memory.set_by_path(["discord_relay_map"], {})
    relay_map = bot.memory.get_by_path(["discord_relay_map"])
    if "discord" not in relay_map:
        relay_map["discord"] = {}
    if "hangouts" not in relay_map:
        relay_map["hangouts"] = {}
    bot.memory.set_by_path(["discord_relay_map"], relay_map)

@client.event
async def on_ready():
    logger.info("Logged in as")
    logger.info(client.user.name)
    logger.info(client.user.id)
    logger.info("------")

# parse commands
# commands supported: !getid, !addrelay, !delrelay, !help
async def parse_command(source, source_id, content):
    tokens = content.split(" ", 1)
    command = tokens[0]
    if command in command_dict:
        logger.debug("command is {}".format(command))
        if len(tokens) == 1:
            await command_dict[command](source, source_id)
        else:
            await command_dict[command](source, source_id, arg_string=tokens[1])

# discord message handler
@client.event
async def on_message(message):
    if message.author.id == client.user.id:
        return
    await parse_command("discord", message.channel.id, message.content)
    content = message.content
    author = str(message.author).rsplit('#', 1)[0]
    new_message = "<b>{}:</b> {}".format(author, content)
    logger.info("message from discord")
    logger.info(new_message)
    for convid in bot_global.conversations.get():
        logger.info("sending to {}".format(convid))
        await bot_global.coro_send_message(convid, new_message)

# Called when the bot starts up
# Need to set up the discord connection and account here
def _start_discord_account(bot):
    loop = asyncio.get_event_loop()
    logger.info("start discord account here")
    discord_config = bot.get_config_option('discord')
    token = discord_config['token']
    coro = client.start(token)
    asyncio.run_coroutine_threadsafe(coro, loop)

# hangouts message handler
def _received_message(bot, event, command):
    new_message = "**{}**: {}".format(event.user.full_name, event.text)
    logger.info("message from hangouts")
    logger.info(new_message)
    # send message to discord here
    for chan in client.get_all_channels():
        if chan.type == discord.ChannelType.text:
            logger.info(chan)
            yield from client.send_message(chan, new_message)

def add_new_relay(bot, discord_server, hangout):
    if not bot.memory.exists(["discord_relay_map"]):
        bot.memory.set_by_path(["discord_relay_map"])
    relay_map = bot.memory.get_by_path(["discord_relay_map"])

    bot.memory.set_by_path(["discord_relay_map"], relay_map)