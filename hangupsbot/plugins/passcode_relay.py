"""hangupsbot plugin to relay messages from one hangout to another

each relay
- has got an identifier
- limits the source messages to one user
- can have multiple source conversations
- can have multiple target conversations

format of the UPDATE_URL file
    each line is one relay,
    each relay has a label and an update url, both separated by colon
'relaylabel1:https://example.com/update
relaylabel2:https://example.com/update2'

format of an update_url file
    source convs, userid and language separated by colon, conversations by comma
'conv0:1000000000000000:DE'
'conv0,conv1:1000000000000000:EN'

as admin: targets can be (un)set with '/bot passcode_relay <a relay identifier>'
    from inside the target conversation

author: @das7pad
modified for passcodes by: @phantomdarkness
"""
import asyncio
import io
import logging

import aiohttp
import hangups

import plugins

logger = logging.getLogger(__name__)

# pylint:disable=line-too-long
UPDATE_URL = 'https://gist.githubusercontent.com/phantomdarkness/8b97f85bc14e21df459279ab86324c70/raw/7c9da03c847d66f52b0e4a3f4bedcddaf7e981d3/available_channel'

def _initialise(bot):
    """update the sources, register the admin command and watch for messages

    Args:
        bot: HangupsBot instance
    """
    if not bot.memory.exists(['passcode_relay']):
        bot.memory.set_by_path(['passcode_relay'], {})
    if not bot.memory.exists(['passcode_relay', '_available_relays']):
        bot.memory.set_by_path(['passcode_relay', '_available_relays'], {})

    asyncio.ensure_future(_update_relays(bot))

    plugins.register_admin_command(['passcode_relay'])
    plugins.register_handler(_on_hangouts_message, "allmessages")

async def _update_relays(bot):
    """fetch the latest passcode relays and update the sync data of each relay

    Args:
        bot: HangupsBot instance

    Returns:
        integer: number of successfully updated relays
    """
    async def _update_relay_source():
        """fetch data from UPDATE_URL to update the sources"""
        try:
            async with aiohttp.request('GET', UPDATE_URL) as resp:
                resp.raise_for_status()
                raw_lines = (await resp.text()).splitlines()
        except aiohttp.ClientError as err:
            logger.error('fetching of sources failed: %s', repr(err))
            return

        relays = [item.split(':', 1) for item in raw_lines]
        path = ['passcode_relay', '_available_relays']
        for label, update_url in relays:
            bot.memory.set_by_path(path + [label], update_url)

    async def _update_single_relay(relay, update_url):
        """update a single relay

        Args:
            relay: string, non empty identifier for a relay
            update_url: string, url of the update data for the relay

        Returns:
            boolean, True if no error occured, otherwise False
        """
        try:
            async with aiohttp.request('GET', update_url) as resp:
                resp.raise_for_status()
                raw = await resp.text()
            source_ids, user, lang = (raw.split(':') + ['EN'])[:3]
            source_ids = source_ids.split(',')
            path = ['passcode_relay', relay]
            if not bot.memory.exists(path):
                blank_mem = {'source_ids': source_ids,
                             'user': user,
                             'lang': lang.upper(),
                             'targets': []}
                bot.memory.set_by_path(path, blank_mem)
            else:
                bot.memory.set_by_path(path + ['source_ids'], source_ids)
                bot.memory.set_by_path(path + ['user'], user)
                bot.memory.set_by_path(path + ['lang'], lang.upper())

            for source_id in source_ids:
                _mute_conv(bot, source_id)
            for target_id in bot.memory.get_by_path(path + ['targets']):
                _mute_conv(bot, target_id)
            return True
        except (KeyError, TypeError, ValueError,
                aiohttp.ClientError) as err:
            logger.error('%s update failed: %s', relay, str(err))
            return False

    await _update_relay_source()
    relays = _get_available_relays(bot)
    results = await asyncio.gather(*[_update_single_relay(relay, update_url)
                                     for relay, update_url in relays.items()],
                                   return_exceptions=True)
    count = sum(item for item in results if not isinstance(item, Exception))
    logger.info('%s/%s relays updated', count, len(relays))
    return count

def _mute_conv(bot, conv_id):
    """disable noise from plugins for the given conversation

    disable mentions, botkeeper-check, commands, autoreplys; set silentmode

    Args:
        bot: HangupsBot instance
        conv_id: string, target conversation to be muted
    """
    if not bot.config.exists(['conversations']):
        bot.config.set_by_path(['conversations'], {})
    if not bot.config.exists(['conversations', conv_id]):
        bot.config.set_by_path(['conversations', conv_id], {})

    config_keys = [('mentions.enabled', False),
                   ('strict_botkeeper_check', False),
                   ('commands_enabled', False),
                   ('silentmode', True)]
    if not bot.config.exists(['conversations', conv_id, 'autoreplies']):
        config_keys.append(('autoreplies_enabled', False))

    for key, value in config_keys:
        bot.config.set_by_path(['conversations', conv_id, key], value)

def _get_available_relays(bot):
    """get the configured relays from memory

    Args:
        bot: HangupsBot instance

    Returns:
        dict, object from memory or empty dict
    """
    try:
        return bot.memory.get_by_path(['passcode_relay', '_available_relays'])
    except (KeyError, TypeError):
        return {}

async def _on_hangouts_message(bot, event):
    """forward a message if passcode and user match a configured relay

    Args:
        bot: HangupsBot instance
        event: event.ConversationEvent instance
    """
    def _get_relay():
        """get the matching relay label for the event message

        Returns:
            string, a configured relay label or an empty string if none matches
        """
        sources = _get_available_relays(bot)
        if not sources:
            # no relays configured
            return ''
        for relay in sources:
            path = ['passcode_relay', relay]
            if (bot.memory.exists(path)
                    and event.user_id.chat_id == bot.memory.get_by_path(
                        path + ['user'])
                    and event.conv_id in bot.memory.get_by_path(
                        path + ['source_ids'])):
                return relay
        # no matching relay
        return ''

    relay = _get_relay()
    if not relay:
        return

    path = ['passcode_relay', relay, 'targets']
    targets = [target for target in bot.memory.get_by_path(path).copy()
               if bot.memory.exists(['convmem', target])]

    if not targets:
        return

    segments = event.conv_event.segments
    uploaded_image = url = None
    try:
        url = event.conv_event.attachments[0]
        async with aiohttp.ClientSession() as session:
            async with session.get(url, allow_redirects=True) as resp:
                resp.raise_for_status()
                if 'content-disposition' not in resp.headers:
                    raise ValueError('no image found')

                # example for a content-disposition:
                # inline;filename="2332232027763463203?account_id=1.png"
                for item in resp.headers['content-disposition'].split(';'):
                    if item.startswith('filename="'):
                        filename = item[10:-1].strip()
                        break
                else:
                    raise ValueError('no filename found')

                # read the raw image data
                raw_image = io.BytesIO(await resp.read())

        # pylint: disable=protected-access
        uploaded_image = await bot._client.upload_image(raw_image, filename)

    except IndexError:
        # no attachments available
        pass
    except (ValueError, aiohttp.ClientError, hangups.NetworkError) as err:
        logger.error('in handling the image url "%s": %s', url, repr(err))
    finally:
        if uploaded_image is None and url is not None:
            # add a fallback
            segments.extend(
                hangups.ChatMessageSegment.from_str('\n%s' % url))

    await asyncio.gather(*[bot.coro_send_message(conv_id, segments,
                                                 image_id=uploaded_image)
                           for conv_id in targets],
                         return_exceptions=True)

async def passcode_relay(bot, event, *args):
    """update relays, add or remove conv from targets of a given relay

    Args:
        bot: HangupsBot instance
        conv_id: string, conversation identifier
        args: tuple of string, additional arguments
    """
    relays = _get_available_relays(bot)
    html = ('<b>Usage:</b>\n{bot_cmd} passcode_relay <i>update</i>\n'
            '    update all configured relays and fetch new one\n'
            '{bot_cmd} passcode_relay <i><relay></i>\n'
            '    <relay> is one of <b>{relay}</b>\n'
            'The conversation will then receive messages if it was no previous '
            'target, otherwise it will be removed from the targets').format(
                # pylint:disable=protected-access
                bot_cmd=bot._handlers.bot_command[0],
                relay=', '.join(relays) or '[no relays available]')
    if (len(args) != 1 or
            (args[0].lower() != 'update' and args[0].lower() not in relays)):
        await bot.coro_send_message(event.conv_id, html)
        return

    if args[0].lower() == 'update':
        successful = await _update_relays(bot)
        text = '{} of {} successfully updated'.format(successful, len(relays))
    else:
        path = ['passcode_relay', args[0].lower(), 'targets']
        targets = bot.memory.get_by_path(path)
        if event.conv_id in targets:
            targets.remove(event.conv_id)
            text = 'RELAY UNSET'
        else:
            targets.append(event.conv_id)
            text = 'RELAY SET'
            _mute_conv(bot, event.conv_id)
        bot.memory.set_by_path(path, targets)

    bot.config.save()
    bot.memory.save()
    await bot.coro_send_message(event.conv_id, text)