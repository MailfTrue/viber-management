import json
import re

import requests
from django.conf import settings
from django.db.models import Q
from django.http.response import HttpResponse
from django.utils.crypto import get_random_string
from viberbot.api.messages import RichMediaMessage, TextMessage, KeyboardMessage, FileMessage
from viberbot.api.viber_requests import ViberConversationStartedRequest
from viberbot.api.viber_requests import ViberMessageRequest

from management.models import Department, BotUser, Employee, Task, TaskReport, TaskEmployee, DayOff
from viber_client import viber, DEFAULT_BUTTON, MIN_API_VERSION
from management.utils import get_default_keyboard, get_task_messages
from datetime import datetime


def new_user(user_id):
    user = BotUser.objects.create(chat_id=user_id)
    process_form(user_id, 'register', user)


message_handlers = []


def message_handler(func=lambda x: True, state=None):
    def decorator(handler):
        handler_dict = {'handler': handler, 'func': func, 'state': state}
        message_handlers.append(handler_dict)
        return handler

    return decorator


def hook(request):
    data = request.body.decode()
    # if not viber.verify_signature(data, request.headers.get('X-Viber-Content-Signature')):
    #     return HttpResponse(status=403)

    viber_request = viber.parse_request(data)
    if isinstance(viber_request, ViberMessageRequest):
        print(type(viber_request), 'processed')
        if viber_request.message.text == '/reset':
            BotUser.objects.filter(chat_id=viber_request.sender.id).delete()
            new_user(viber_request.sender.id)
        else:
            user = BotUser.objects.get(chat_id=viber_request.sender.id)
            if str(user.state).startswith('form#'):
                form_key = user.state.split('#')[1]
                process_form(viber_request.sender.id, form_key, user, text=viber_request.message.text)
            else:
                for handler in message_handlers:
                    if handler['state'] == user.state:
                        handler['handler'](viber_request, user)
                        break
                    elif handler['func'](viber_request, user):
                        handler['handler'](viber_request, user)
                        break

    elif isinstance(viber_request, ViberConversationStartedRequest):
        new_user(viber_request.user.id)

    return HttpResponse(status=200)


FORMS = {
    'register': {
        'questions': {
            'full_name': {
                'type': str,
                'question': 'Добрый день! Введите ваше ФИО'
            },
            'phone': {
                'type': 're',
                'regex': r'^[+]*[(]{0,1}[0-9]{1,4}[)]{0,1}[-\s\./0-9]*$',
                'question': 'Введите ваш номер телефона без лишних символов'
            },
            'departments': {
                'type': 'choices',
                'question': 'Выберете отделы, в которых Вы работаете, нажмите «Завершить»',
                'choices': Department.objects.values_list('id', 'title'),
                'multi': True
            }
        },
        'final_text': 'Вы зарегистрированы в боте сотрудников компании. Ожидайте активации аккаунта.'
    },
    'create-weekend': {
        'questions': {
            'start_date': {
                'type': 're',
                'regex': r'[0-3]?\d\.[0-1]\d.20\d\d',
                'question': 'Введите дату начала выходного, например: 20.12.2020'
            },
            'end_date': {
                'type': 're',
                'regex': r'[0-3]?\d\.[0-1]\d.20\d\d',
                'question': 'Введите дату окончания выходного, например: 25.12.2020'
            }
        },
        'final_text': 'Заявка на выходной оставлена'
    }
}


def process_form(chat_id, form_key, user, text=None):
    form = FORMS[form_key]
    if user.state.startswith('form#'):
        data = json.loads(user.state.split('#')[2])
    else:
        data = {}
    questions = form['questions']
    fields = list(questions.keys())
    field = data.get('current')
    change_field = True
    field_value = text
    if not field:
        field = fields[0]
    else:
        valid = False
        if questions[field]['type'] == 're':
            match = re.fullmatch(questions[field]['regex'], text)
            valid = bool(match)
        elif questions[field]['type'] == 'choices':
            multi = questions[field]['multi']
            change_field = not multi
            if text:
                if not text.startswith('/form_choice_end'):
                    checked = data.get(field) or []
                    try:
                        choice_id = text.split('#')[1]
                        if choice_id not in checked:
                            checked.append(choice_id)
                        else:
                            checked.remove(choice_id)
                        data[field] = checked
                        print(checked)
                    except IndexError:
                        pass
                else:
                    change_field = True
                    valid = True
                    field_value = data.get(field) or []
        else:
            try:
                questions[field]['type'](text)
                valid = True
            except (ValueError, TypeError):
                pass
        if valid and change_field:
            data[field] = field_value
            try:
                field = fields[fields.index(field) + 1]
            except IndexError:
                field = None

    if field:
        field_changed = data.get('current') != field
        data['current'] = field
        user.state = f'form#{form_key}#{json.dumps(data)}'
        user.save()
        messages = [TextMessage(text=questions[field]['question'])]
        if questions[field].get('choices'):
            checked = data.get(field) or []
            choices = questions[field]['choices']
            keyboard = {
                "Buttons": [
                    *[
                        {
                            **DEFAULT_BUTTON,
                            "Columns": 6,
                            "Rows": 1,
                            "ActionBody": f"/form_choice#{k}",
                            "Text": ('✅' if str(k) in checked else '') + f"<b>{v}</b>"
                        } for k, v in choices
                    ],
                    {
                        **DEFAULT_BUTTON,
                        "BgColor": "#2cc429",
                        "ActionBody": f"/form_choice_end",
                        "Text": "<b>Завершить</b>",
                    }
                ]
            }
            keyboard_message = KeyboardMessage(keyboard=keyboard, min_api_version=MIN_API_VERSION)
            if field_changed:
                messages.append(keyboard_message)
            else:
                messages = [keyboard_message]
        viber.send_messages(chat_id, messages)
    else:
        viber.send_messages(chat_id, [
            TextMessage(text=form['final_text'], keyboard=get_default_keyboard(user.employee), min_api_version=MIN_API_VERSION)
        ])
        user.state = BotUser.default_state
        user.save()

        del data['current']
        if form_key == 'register':
            viber.send_messages(chat_id, [
                TextMessage(text=f'Ваш ID: {chat_id}', keyboard=get_default_keyboard(user.employee))
            ])
            e = Employee.objects.create(
                full_name=data['full_name'],
                phone=data['phone'],
                bot_user=user
            )
            print(data['departments'])
            e.departments.set(data['departments'])
        elif form_key == 'create-weekend':
            DayOff.objects.create(employee=user.employee,
                                  start_date=datetime.strptime(data['start_date'], '%d.%m.%Y'),
                                  end_date=datetime.strptime(data['end_date'], '%d.%m.%Y'))


@message_handler(lambda r, u: (r.message.text or '').startswith('/accept_task#'))
def accept_task(r, user):
    task_id = r.message.text.split('#')[-1]
    task = Task.objects.get(id=task_id)
    TaskEmployee.objects.update_or_create({'accepted': True}, task=task, employee=user.employee)
    messages = [
        TextMessage(text=f"Вы приняли задачу \"{task.name}\""),
        TextMessage(text=f"{task.name}\n\n{task.text}")
    ]
    if task.file:
        messages.append(FileMessage(media=settings.VIBER_MEDIA_HOST + task.file.url, file_name=task.file.name,
                                    size=task.file.size, min_api_version=MIN_API_VERSION))
    rich_media = {
        "ButtonsGroupRows": 1,
        "ButtonsGroupColumns": 3,
        "Buttons": [
            {
                **DEFAULT_BUTTON,
                "Columns": 3,
                "ActionType": "reply",
                "Silent": "true",
                "ActionBody": f"/start_report_task#{task.id}",
                "Text": "<b>Отчёт</b>",
            }
        ]
    }
    messages.append(RichMediaMessage(rich_media=rich_media, min_api_version=MIN_API_VERSION, keyboard=get_default_keyboard(user.employee)))
    viber.send_messages(r.sender.id, messages)


@message_handler(lambda r, u: (r.message.text or '').startswith('/start_report_task#'))
def report_task(r, user):
    task_id = r.message.text.split('#')[-1]
    task = Task.objects.get(id=task_id)
    viber.send_messages(r.sender.id, [TextMessage(text='Введите текст')])
    data = {'id': task.id}
    user.state = f'report_task#w-text#{json.dumps(data)}'
    user.save()


@message_handler(lambda r, u: u.state.startswith('report_task') or (r.message.text or '').startswith('/report_task#'))
def report_handler(r, user):
    data = json.loads(user.state.split('#')[2])
    report_step = user.state.split('#')[1]
    next_step = ''
    next_state = ''
    messages = []
    if report_step == 'w-text':
        data['text'] = r.message.text
        messages.append(TextMessage(text='Текст принят'))
    elif report_step == 'w-photo':
        filename = get_random_string(32) + '.jpg'
        with open(f'media/{filename}', 'wb') as handle:
            response = requests.get(r.message.media, stream=True)
            for block in response.iter_content(1024):
                if not block:
                    break

                handle.write(block)
        data['photo'] = settings.VIBER_MEDIA_HOST + settings.MEDIA_URL + filename
        messages.append(TextMessage(text='Фото принято'))

    if (r.message.text or '').startswith('/report_task#'):
        report_step = r.message.text.split('#')[1]
        if report_step == 'photo':
            messages.append(TextMessage(text='Приложите фото'))
            next_step = 'w-photo'
        elif report_step == 'delete':
            next_state = BotUser.default_state
            messages.append(TextMessage(text='Отчет удален', keyboard=get_default_keyboard(user.employee)))
        elif report_step == 'send':
            te = TaskEmployee.objects.get(task_id=data['id'], employee=user.employee, finished=False)
            TaskReport.objects.create(task_employee=te, text=data['text'], photo=data['photo'])
            next_state = BotUser.default_state
            messages.append(TextMessage(text='Отчет отправлен на утверждение', keyboard=get_default_keyboard(user.employee)))

    if not next_state:
        if not next_step:
            report_keyboard = {
                "Buttons": [
                    {
                        **DEFAULT_BUTTON,
                        "BgColor": "#2cc429",
                        "ActionBody": f"/report_task#send",
                        "Text": "<b>Отправить</b>",
                    },
                    {
                        **DEFAULT_BUTTON,
                        "BgColor": "#2cc429",
                        "ActionBody": f"/report_task#photo",
                        "Text": "<b>Приложить фото</b>",
                    },
                    {
                        **DEFAULT_BUTTON,
                        "BgColor": "#2cc429",
                        "ActionBody": f"/report_task#delete",
                        "Text": "<b>Удалить отчёт</b>",
                    }
                ]
            }
            messages.append(KeyboardMessage(keyboard=report_keyboard, min_api_version=MIN_API_VERSION))
        user.state = f"report_task#{next_step}#{json.dumps(data)}"
        user.save()
    else:
        user.state = next_state
        user.save()
    if messages:
        viber.send_messages(r.sender.id, messages)


@message_handler(lambda r, u: (r.message.text or '').startswith('/tasks'))
def tasks_list(r, user):
    tasks_query = {
        'active': Q(accepted=True, finished=False),
        'ignored': Q(accepted=False, finished=False)
    }[r.message.text.split('.')[1]]
    tes = TaskEmployee.objects.filter(tasks_query)
    buttons = []
    default_button = {**DEFAULT_BUTTON, 'BgColor': None}
    for te in tes:
        buttons += [
            {
                **default_button,
                "Columns": 6,
                "ActionType": "reply",
                "Silent": "true",
                "ActionBody": f"/task#{te.task.id}",
                "Text": f"<b>{te.task.name}</b>",
            },
            {
                **default_button,
                "Rows": 4,
                "Columns": 6,
                "ActionType": "reply",
                "Silent": "true",
                "ActionBody": f"/task#{te.task.id}",
                "TextSize": "regular",
                "Text": f"{te.task.text[:300]}"
            },
            {
                **default_button,
                "Columns": 6,
                "ActionType": "reply",
                "Silent": "true",
                "ActionBody": f"/task#{te.task.id}",
                "Text": "<b>Подробнее</b>",
            }
        ]
    if buttons:
        rich_media = {
            "ButtonsGroupRows": 6,
            "ButtonsGroupColumns": 6,
            "BgColor": '#ffffff',
            "Buttons": buttons
        }
        viber.send_messages(r.sender.id, RichMediaMessage(rich_media=rich_media, min_api_version=MIN_API_VERSION, keyboard=get_default_keyboard(user.employee)))
    else:
        viber.send_messages(r.sender.id, TextMessage(text='Пусто', keyboard=get_default_keyboard(user.employee), min_api_version=MIN_API_VERSION))


@message_handler(lambda r, u: (r.message.text or '').startswith('/task#'))
def task_handler(r, user):
    task = Task.objects.get(id=r.message.text.split('#')[1])
    messages = get_task_messages(task)
    messages.append(KeyboardMessage(keyboard=get_default_keyboard(user.employee), min_api_version=MIN_API_VERSION))
    viber.send_messages(r.sender.id, messages)


@message_handler(lambda r, u: (r.message.text or '').startswith('/weekend.create'))
def create_weekend(r, user):
    process_form(r.sender.id, 'create-weekend', user)


@message_handler(lambda r, u: (r.message.text or '').startswith('/menu') or True)
def menu_handler(r, user):
    viber.send_messages(r.sender.id, [KeyboardMessage(keyboard=get_default_keyboard(user.employee), min_api_version=MIN_API_VERSION)])

