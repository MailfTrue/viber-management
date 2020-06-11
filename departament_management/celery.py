from celery import Celery
import os
from celery.schedules import crontab


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'departament_management.settings')

app = Celery('departament_management')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

app.conf.beat_schedule = {
    'checking-new-tasks': {
        'task': 'management.tasks.send_tasks',
        'schedule': crontab()
    },
    'checking-ignored-tasks': {
        'task': 'management.tasks.send_ignored_tasks',
        'schedule': crontab(minute="*/10")
    },
    'checking-expired-tasks': {
        'task': 'management.tasks.send_expired_tasks',
        'schedule': crontab(minute="*/5")
    },
    'checking-delayed-tasks': {
        'task': 'management.tasks.send_delayed_tasks',
        'schedule': crontab(minute="0")
    },
}
app.conf.timezone = 'Europe/Moscow'
