import asyncio
from hangups.user import User

@asyncio.coroutine
def _update_unknown_users(bot):
    for key in bot._user_list._user_dict:
        user_object = bot._user_list._user_dict[key]

        if user_object.first_name == "unknown":
            user_id = key.chat_id
            response = yield from bot._client.getentitybyid([user_id])
            try:
                display_name = response['entity'][0]['properties']['display_name']
                first_name = response['entity'][0]['properties']['first_name']
                bot._user_list._user_dict[key] = User(key, display_name, first_name, None, [], False)
                print("refreshusers() {} {}".format(user_id, display_name))
            except Exception as e:
                print("refreshusers() {} {}".format(user_id, e))

    print("refreshusers() completed")


@asyncio.coroutine
def _membership_change(bot, event, command):
    yield from _update_unknown_users(bot)


def _initialise(Handlers, bot=None):
    Handlers.register_admin_command(["refreshusers", "dumpusers"])

    if bot.get_config_option('force_userlist_autorefresh'):
        Handlers.register_handler(_membership_change, type="membership", priority=10)
        asyncio.async(_update_unknown_users(bot))

    return []


def refreshusers(bot, event, *args):
    yield from _update_unknown_users(bot)


def dumpusers(bot, event, *args):
    count = 0
    for key in bot._user_list._user_dict:
        user_object = bot._user_list._user_dict[key]
        if len(args) == 0 or " ".join(args).lower() in user_object.full_name.lower() or " ".join(args) in user_object.id_.chat_id:
            print("dumpusers(): {} | {} {}".format(user_object.id_.chat_id, user_object.first_name, user_object.full_name))
            count = count + 1
    print("dumpusers(): {} users".format(count))
