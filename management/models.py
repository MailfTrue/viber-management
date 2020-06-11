from django.db import models
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils import timezone
from viber_client import send_confirm_notification
from django.db.models.signals import post_save, post_init


class BotUser(models.Model):
    chat_id = models.CharField(max_length=64)
    state = models.TextField()

    @property
    def default_state(self):
        return BotUser._meta.get_field('state').default

    def __str__(self):
        return self.chat_id


class Employee(models.Model):
    full_name = models.CharField('ФИО', max_length=32)
    phone = models.CharField('Телефон', max_length=32)
    departments = models.ManyToManyField('Department', verbose_name='Отделы')
    joined_at = models.DateTimeField('Дата подключения', null=True, blank=True)
    bot_user = models.OneToOneField('BotUser', on_delete=models.CASCADE, verbose_name='Viber аккаунт', null=True,
                                    blank=True)
    user = models.OneToOneField(get_user_model(), on_delete=models.CASCADE, verbose_name='Аккаунт в админ панели',
                                null=True, blank=True)
    managed_departments = models.ManyToManyField('Department', verbose_name='Отделы, которыми может управлять',
                                                 related_name='managed_departments', blank=True)
    confirmed = models.BooleanField('Подтвержден', default=False)
    previous_confirmed = None

    @staticmethod
    def employee_accepted(sender, **kwargs):
        instance = kwargs.get('instance')
        created = kwargs.get('created')
        if instance.bot_user.chat_id:
            if not instance.previous_confirmed and instance.confirmed:
                send_confirm_notification(instance.bot_user.chat_id)

    @property
    def dayoff_today(self):
        now = timezone.localtime(timezone.now())
        return DayOff.objects.filter(start_date__lt=now, end_date__gt=now, employee=self, confirmed=True).count() > 0

    @staticmethod
    def remember_employee_accept(sender, **kwargs):
        instance = kwargs.get('instance')
        instance.previous_confirmed = instance.confirmed

    def __str__(self):
        return f"{self.full_name}, {self.phone}"

    class Meta:
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'


post_save.connect(Employee.employee_accepted, sender=Employee)
post_init.connect(Employee.remember_employee_accept, sender=Employee)


class Department(models.Model):
    title = models.CharField('Название отдела', max_length=32)
    report_managers = models.ManyToManyField('Employee', verbose_name='Принимающие отчеты')

    def __str__(self):
        return self.title

    class Meta:
        ordering = 'title',
        verbose_name = 'Отдел'
        verbose_name_plural = 'Отделы'


class Task(models.Model):
    name = models.CharField('Название задачи', max_length=32)
    text = models.TextField('Текст задачи')
    file = models.FileField('Файл', null=True, blank=True)
    sent = models.BooleanField(default=False)
    deadline = models.DateTimeField('Срок выполнения', null=True, blank=True)
    start_date = models.DateTimeField(
        'Время отправки задачи', help_text='оставьте пустым, если нужно отправить сразу', null=True, blank=True)
    departments = models.ManyToManyField('Department', verbose_name='Отделы', blank=True)
    employees = models.ManyToManyField('Employee', verbose_name='Исполнители', blank=True)

    @property
    def all_employees(self):
        employees_ids = self.employees.values_list('id', flat=True)
        employees = Employee.objects.filter(Q(id__in=employees_ids) | Q(departments__in=self.departments.all()))
        return Employee.objects.filter(id__in=employees.values_list('id', flat=True))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'


class TaskEmployee(models.Model):
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE)
    task = models.ForeignKey('Task', on_delete=models.CASCADE)
    accepted = models.BooleanField(default=False)
    finished = models.BooleanField(default=False)
    deadline_expired_notif = models.BooleanField(editable=False, default=False)


class TaskReport(models.Model):
    task_employee = models.ForeignKey('TaskEmployee', on_delete=models.CASCADE)
    text = models.TextField('Текст')
    photo = models.URLField('Фото', null=True, blank=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    checked = models.BooleanField('Проверен', default=False)
    accepted = models.BooleanField('Утвержден', default=False)
    answer_text = models.TextField('Текст', null=True, blank=True)
    answer_file = models.FileField('Файл', null=True, blank=True)

    def __str__(self):
        return f'Отчет на задачу {self.task_employee.task}'

    class Meta:
        verbose_name = 'Отчет'
        verbose_name_plural = 'Отчеты'


class WaitingTaskReportManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(checked=False)


class WaitingTaskReport(TaskReport):
    objects = WaitingTaskReportManager()

    class Meta:
        proxy = True
        verbose_name = 'Отчет на утверждение'
        verbose_name_plural = 'Отчеты на утверждение'


class AcceptedTaskReportManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(checked=True, accepted=True)


class AcceptedTaskReport(TaskReport):
    objects = AcceptedTaskReportManager()

    class Meta:
        proxy = True
        verbose_name = 'Полный отчет'
        verbose_name_plural = 'Полные отчеты'


class DepartmentManager(models.Model):
    employee = models.OneToOneField('Employee', verbose_name='Сотрудник', on_delete=models.CASCADE)
    departments = models.ManyToManyField('Department', verbose_name='Отделы')

    def __str__(self):
        return self.employee.full_name

    class Meta:
        verbose_name = 'Управляющий'
        verbose_name_plural = 'Управляющие'


class DayOff(models.Model):
    employee = models.ForeignKey('Employee', verbose_name='Сотрудник', on_delete=models.CASCADE)
    start_date = models.DateField('Начало выходных')
    end_date = models.DateField('Конец выходных')
    confirmed = models.BooleanField('Утвержден', default=False)
    checked = models.BooleanField('Проверен', default=False)

    def __str__(self):
        return f"Выходной у {self.employee} с {self.start_date} по {self.end_date}"

    class Meta:
        verbose_name = 'Выходной'
        verbose_name_plural = 'Выходные'


class DelayedTask(models.Model):
    task = models.ForeignKey('Task', verbose_name='Сотрудник', on_delete=models.CASCADE)
    employee = models.ForeignKey('Employee', verbose_name='Сотрудник', on_delete=models.CASCADE)
