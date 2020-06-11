from viberbot.api.messages import TextMessage, RichMediaMessage
from viber_client import viber, DEFAULT_BUTTON, MIN_API_VERSION
from management.models import DayOff, DelayedTask, TaskEmployee
from django.utils import timezone


def get_task_messages(task):
    text = f"Вам поставлена новая задача «{task.name}»"
    messages = [TextMessage(text=text)]
    accept_rich_media = {
        "BgColor": "#69C48A",
        "ButtonsGroupRows": 1,
        "ButtonsGroupColumns": 3,
        "Buttons": [
            {
                **DEFAULT_BUTTON,
                "Columns": 3,
                "ActionType": "reply",
                "Silent": "true",
                "ActionBody": f"/accept_task#{task.id}",
                "Text": "<b>Принять</b>",
            }
        ]
    }
    messages.append(RichMediaMessage(rich_media=accept_rich_media, alt_text='Принять', min_api_version=MIN_API_VERSION))
    return messages


def get_default_keyboard(employee):
    default_button = {
        "Rows": 1,
        "ActionType": "reply",
        "TextVAlign": "middle",
        "TextHAlign": "middle",
        "TextSize": "regular",
        "BgColor": "#2cc429",
    }
    keyboard = {
        "Buttons": [
            {
                **default_button,
                "Columns": 3,
                "ActionBody": "/tasks.ignored",
                "Text": "<b>Непринятые задачи</b>",
            },
            {
                **default_button,
                "Columns": 3,
                "ActionBody": f"/tasks.active",
                "Text": "<b>Задачи на исполнении</b>",
            },
            {
                **default_button,
                "ActionBody": f"/weekend.create",
                "Text": "<b>Выходной</b>",
            }
        ]
    }
    return keyboard


def send_task_to_employee(task, employee):
    now = timezone.localtime(timezone.now())
    have_dayoff = DayOff.objects.filter(start_date__lt=now, end_date__gt=now, employee=employee).count() > 0
    if not have_dayoff:
        TaskEmployee.objects.get_or_create(employee=employee, task=task)
        if employee.bot_user:
            messages = get_task_messages(task)
            viber.send_messages(employee.bot_user.chat_id, messages)
    return not have_dayoff
