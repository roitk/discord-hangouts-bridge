import asyncio, logging

import plugins

logger = logging.getLogger(__name__)

def _initialize(bot):
    _start_discord_account(bot)
    plugins.register_handler(_received_message, type="message", priority=50)

# Called when the bot starts up
# Need to set up the discord connection and account here
def _start_discord_account(bot):
    logger.info("start discord account here")

# Send message to discord
def _received_message(bot, event, command):
    logger.info("message handler")