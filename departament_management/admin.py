from django.contrib.admin import AdminSite
from management.models import TaskEmployee, TaskReport, Employee
from django.utils import timezone


class CustomAdminSite(AdminSite):
    site_header = 'Панель управления'
    site_title = 'Бот'
    index_title = 'Главная'
    site_url = None

    def index(self, request, extra_context=None):
        now = timezone.localtime(timezone.now())
        colors = {
            'red': 'rgb(255, 99, 132)',
            'orange': 'rgb(255, 159, 64)',
            'yellow': 'rgb(255, 205, 86)',
            'green': 'rgb(75, 192, 192)',
            'blue': 'rgb(54, 162, 235)',
            'purple': 'rgb(153, 102, 255)',
            'grey': 'rgb(201, 203, 207)'
        }
        employees = Employee.objects.all()
        employees_working = 0
        for employee in employees:
            if not employee.dayoff_today:
                employees_working += 1
        managers = employees.exclude(managed_departments=None)
        managers_working = 0
        for manager in managers:
            if not manager.dayoff_today:
                managers_working += 1
        charts = [
            {  # График по задачам
                'data': [
                    TaskEmployee.objects.filter(accepted=True, finished=False).count(),  # В работе
                    TaskEmployee.objects.filter(accepted=False).count(),  # Не принято
                    TaskEmployee.objects.filter(finished=False, task__deadline__lt=now).count(),  # Не сданы в срок
                    TaskReport.objects.filter(checked=False).count(),  # На утверждении
                ],
                'colors': list(colors.values())[:4],
                'labels': {
                    # 'Задач в работе': 'https://mailf-proxy.easyprbot.com/admin/management/task/?active=1',
                    # 'Задач не принято': 'https://mailf-proxy.easyprbot.com/admin/management/employee/?accepted=0',
                    # 'Задач не сданы в срок': 'https://mailf-proxy.easyprbot.com/admin/management/employee/?expired=1',
                    # 'Задач на утверждении': 'https://mailf-proxy.easyprbot.com/admin/management/employee/?finished=1',
                    'Задач в работе': '#',
                    'Задач не принято': '#',
                    'Задач не сданы в срок': '#',
                    'Задач на утверждении': '#'
                }
            },
            {  # График по сотрудникам
                'data': [
                    employees.count(),  # Всего
                    employees_working,  # На работе
                    employees.count() - employees_working  # Выходной
                ],
                'colors': list(colors.values())[:3],
                'labels': {
                    'Сотрудников всего': 'https://mailf-proxy.easyprbot.com/admin/management/employee/',
                    'Сотрудников на работе': 'https://mailf-proxy.easyprbot.com/admin/management/employee/?working=1',
                    'Сотрудников отдыхает': 'https://mailf-proxy.easyprbot.com/admin/management/employee/?working=0'
                }
            },
            {  # График по управляющим
                'data': [
                    managers.count(),  # Всего
                    managers_working,  # На работе
                    managers.count() - managers_working  # Выходной
                ],
                'colors': list(colors.values())[:3],
                'labels': {
                    'Управляющих всего': 'https://mailf-proxy.easyprbot.com/admin/management/employee/?is_manager=1',
                    'Управляющих на работе': 'https://mailf-proxy.easyprbot.com/admin/management/employee/?is_manager=1&working=1',
                    'Управляющих отдыхает': 'https://mailf-proxy.easyprbot.com/admin/management/employee/?is_manager=1&working=0'
                }
            },
        ]
        extra_context = {
            'charts': charts,
            'chart_width': str(round(100 / len(charts))) + '%'
        }
        return super().index(request, extra_context)


site = CustomAdminSite()
