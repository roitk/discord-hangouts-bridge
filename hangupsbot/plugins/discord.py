import asyncio, logging

import discord

import plugins

client = discord.Client()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
bot_global = None

def _initialize(bot):
    plugins.register_handler(_received_message, type="message", priority=50)
    global bot_global
    bot_global = bot
    _start_discord_account(bot)

@client.event
async def on_ready():
    logger.info('Logged in as')
    logger.info(client.user.name)
    logger.info(client.user.id)
    logger.info('------')

# discord message handler
@client.event
async def on_message(message):
    content = message.content
    author = str(message.author).rsplit('#', 1)[0]
    new_message = "<b>{}:</b> {}".format(author, content)
    logger.info("message from discord")
    logger.info(new_message)
    for convid in bot_global.conversations.get():
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