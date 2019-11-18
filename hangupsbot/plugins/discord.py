import asyncio, logging

import discord

import plugins

CLIENT = discord.Client()
logging.basicConfig(format="%(levelname)s:%(name)s:%(lineno)d:%(message)s",level=logging.INFO)
LOGGER = logging.getLogger(__name__)

async def send_message_invariant(source, source_id, message):
    """Sends a message to either discord or hangouts"""
    LOGGER.info("Sending message to %s conversation %s: %s", source, source_id, message)
    if source == "discord":
        channel = CLIENT.get_channel(source_id)
        #await CLIENT.send_message(CLIENT.get_channel(source_id), message)
        await channel.send(message)
    elif source == "hangouts":
        await CLIENT.hangouts_bot.coro_send_message(source_id, message)

async def do_help(source, source_id):
    """Send a list of commands back to the sender"""
    help_message = "!addrelay <other_id>, !delrelay <other_id>, !getid, !help"
    await send_message_invariant(source, source_id, help_message)

async def do_getid(source, source_id):
    """Send this conversation's id back to the sender"""
    await send_message_invariant(source, source_id, "This {} channel id: {}".format(source, source_id))

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
    await send_message_invariant(source, source_id, "Relay added to {} channel {}.".format(target, target_id))

async def do_delrelay(source, source_id, **args):
    """Delete a relay"""
    target = "discord" if source == "hangouts" else "hangouts"
    if "arg_string" not in args:
        await send_message_invariant(source, source_id, "usage: !delrelay <{}_id>".format(target))
    arg_string = args["arg_string"]
    target_id = arg_string.split(" ", 1)[0]
    LOGGER.info("Relay delete request received from %s channel %s to %s channel %s.",
                source,
                source_id,
                target,
                target_id)
    relay_map = CLIENT.hangouts_bot.memory.get_by_path(["discord_relay_map"])
    if source_id not in relay_map[source]:
        await send_message_invariant(source, source_id, "No relays found for this channel.")
        return
    if target_id not in relay_map[target]:
        await send_message_invariant(source, source_id, "There are no relays to that channel.")
        return
    if target_id not in relay_map[source][source_id] or source_id not in relay_map[target][target_id]:
        msg = "There is no relay between this channel and {} channel {}.".format(target, target_id)
        await send_message_invariant(source, source_id, msg)
        return
    del relay_map[source][source_id][target_id]
    if not relay_map[source][source_id]:
        del relay_map[source][source_id]
    del relay_map[target][target_id][source_id]
    if not relay_map[target][target_id]:
        del relay_map[target][target_id]
    CLIENT.hangouts_bot.memory.set_by_path(["discord_relay_map"], relay_map)
    CLIENT.relay_map = relay_map
    await send_message_invariant(source, source_id, "Relay between {} channel {} and this channel deleted.".format(target, target_id))

async def do_relaydump(source, source_id):
    """Print a list of relay maps"""
    msg = "Here are all of my relays:"
    await send_message_invariant(source, source_id, msg)
    await send_message_invariant(source, source_id, str(CLIENT.relay_map))

COMMAND_DICT = {
    "!help": do_help,
    "!getid": do_getid,
    "!addrelay": do_addrelay,
    "!delrelay": do_delrelay,
    "!relaydump": do_relaydump
}

def _initialize(bot):
    """Hangoutsbot plugin initialization function"""
    plugins.register_handler(_received_message, type="message", priority=50)
	#plugins.register_user_command(["getid"])
    #plugins.register_admin_command(["addrelay","delrelay","relaydump"])
    CLIENT.hangouts_bot = bot
    _start_discord_account(bot)
    _init_discord_map(bot)

def _start_discord_account(bot):
    """Log in to discord using token stored in config file"""
    loop = asyncio.get_event_loop()
    LOGGER.info("start discord account here")
    discord_config = bot.get_config_option('discord')
    token = discord_config['token']
    coro = CLIENT.start(token)
    asyncio.run_coroutine_threadsafe(coro, loop)

def _init_discord_map(bot):
    """Creates a relay map if it doesn't exist and reads it into memory"""
	#discord_config = bot.get_config_option('discord')
	#print(discord_config)
	#relay_map = discord_config["relays"]
	#LOGGER.info(relay_map)
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
    """Discord ready handler"""
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

@CLIENT.event
async def on_message(message):
    """Discord message handler"""
    channel = message.channel
    LOGGER.info("Rx Discord Message on channel %s", channel)

    # Prevent message loopback
    if message.author.id == CLIENT.user.id:
        return

    # Don't send commands through the relay
    if await parse_command("discord", message.channel.id, message.clean_content):
        return

    # Only send regular messages
    if message.type != discord.MessageType.default:
        return
    
    content = message.clean_content
    author = str(message.author).rsplit('#', 1)[0]
    if message.author.nick:
        author = str(message.author.nick)
    new_message = "<b>{}:</b> {}".format(author, content)
    LOGGER.info("message from discord")
    LOGGER.info(new_message)
    LOGGER.info("Channel ID: %d" %(message.channel.id))
    if str(message.channel.id) in CLIENT.relay_map["discord"]:
        for convid in CLIENT.relay_map["discord"][str(message.channel.id)]:
            LOGGER.info("sending to {}".format(convid))
            await CLIENT.hangouts_bot.coro_send_message(convid, new_message)

def encode_mentions(message, server):
    """Encode mentions so they're not just displayed as plaintext"""
    tokens = ['<@' + server.get_member_named(token[1:]).id + '>'
        if token.startswith('@') and server.get_member_named(token[1:]) 
        else token 
    for token in message.split()]
    return ' '.join(tokens)

def _received_message(bot, event, command):
    """Hangouts message handler"""
    command = yield from parse_command("hangouts", event.conv_id, event.text)
    if command:
        return
    new_message = "**{}**: {}".format(event.user.full_name, event.text)
    LOGGER.info("message from hangouts conversation %s", event.conv_id)
    LOGGER.info(new_message)

    # Send message to discord
    if event.conv_id in CLIENT.relay_map["hangouts"]:
        conIDSent = []
        for conv_id in CLIENT.relay_map["hangouts"][event.conv_id]:
            channel_id = int(conv_id)
            #LOGGER.info(conv_id)
            LOGGER.info("Channel ID: %d",int(conv_id))
            chan = CLIENT.get_channel(channel_id)
            print(chan)
            if chan in conIDSent:
                break
            server = chan.guild

            # Properly encode mentions
            new_message = encode_mentions(new_message, server)

            LOGGER.info(chan)

            # Only send to text channels, not voice and other
            if chan.type == discord.ChannelType.text:
                LOGGER.info(chan)
                yield from chan.send(new_message)
                conIDSent.append(chan)
