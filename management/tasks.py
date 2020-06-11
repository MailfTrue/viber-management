from departament_management.celery import app
from django.utils import timezone
from datetime import timedelta
from .models import Task, TaskEmployee, DayOff, DelayedTask, Employee
from viberbot.api.messages import *
from django.conf import settings
from .utils import get_task_messages, send_task_to_employee
from viber import viber, DEFAULT_BUTTON, MIN_API_VERSION


@app.task
def send_tasks():
    now = timezone.localtime(timezone.now()).replace(second=0)
    tasks = Task.objects.filter(start_date__lt=now, sent=False)
    for task in tasks:
        task.sent = True
        task.save()
        for employee in task.all_employees:
            task_sent = send_task_to_employee(task, employee)
            if not task_sent:
                DelayedTask.objects.create(task=task, employee=employee)


@app.task
def send_delayed_tasks():
    for delayed_task in DelayedTask.objects.all():
        task_sent = send_task_to_employee(delayed_task.task, delayed_task.employee)
        if task_sent:
            delayed_task.delete()


@app.task
def send_ignored_tasks():
    after = timezone.localtime(timezone.now()).replace(second=0) - timedelta(minutes=30)
    tes = TaskEmployee.objects.filter(task__start_date__lte=after, accepted=False)
    for te in tes:
        task = te.task
        text = f"Вы не приняли к выполнению задачу «{task.name}»." \
               f"Прошу вас перейти по кнопке «Непринятые задачи» и приступить к выполнению задачи!"
        messages = [TextMessage(text=text)]
        if te.employee.bot_user:
            viber.send_messages(te.employee.bot_user.chat_id, messages)


@app.task
def send_expired_tasks():
    now = timezone.localtime(timezone.now())
    tes = TaskEmployee.objects.filter(task__deadline__lt=now, finished=False, deadline_expired_notif=False)
    for te in tes:
        task = te.task
        te.deadline_expired_notif = True
        te.save()
        employee_departments = te.employee.departments.all()
        for manager in Employee.objects.filter(managed_departments__in=employee_departments):
            text = f'{manager.full_name} просрочил задачу {task.name}'
            viber.send_messages(manager.bot_user.chat_id, TextMessage(text=text))
        text = f"Вы просрочили исполнение задачи «{task.name}», Прошу вас перейти по кнопке" \
               f" «Задачи на исполнении» и приступить к выполнению задачи поскорее и прислать отчет!"
        messages = [TextMessage(text=text)]
        if te.employee.bot_user:
            viber.send_messages(te.employee.bot_user.chat_id, messages)


