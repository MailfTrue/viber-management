from viberbot import BotConfiguration, Api
from viberbot.api.messages import TextMessage

bot_configuration = BotConfiguration(
    name='managementbot',
    avatar='https://share.cdn.viber.com/pg_download?id=0-04-01-ea672a93b3b4c55ee962c62e50b0642f8626a9b4aff13d78f521e22f7b9f58e9&filetype=jpg&type=icon',
    auth_token='4b9d9778eb27dd1a-c1bc8336fab52da8-1e9da9b27e4b3ed1'
)
viber = Api(bot_configuration)


DEFAULT_BUTTON = {
    "Columns": 6,
    "Rows": 1,
    "ActionType": "reply",
    "Silent": "true",
    "BgColor": "#4287f5",
    "TextVAlign": "middle",
    "TextHAlign": "middle",
    "TextSize": "large",
}
MIN_API_VERSION = 8


def send_confirm_notification(chat_id):
    viber.send_messages(chat_id, [TextMessage(text='Ваш аккаунт подтвержден')])