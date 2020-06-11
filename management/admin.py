from django.contrib.admin import ModelAdmin, register, site, SimpleListFilter
from collections.abc import Iterable
from django.db.models import Manager, Q
from django.utils.html import mark_safe, format_html
from django.http.response import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.core.exceptions import ValidationError
from django.urls import reverse, path, re_path
from django.utils.crypto import get_random_string
from django.utils import timezone
from departament_management.admin import site
from .models import *
from .forms import DepartmentAdminForm, DepartmentManagerAdminForm, CorrectTaskReport


class EmployeeWorkingFilter(SimpleListFilter):
    parameter_name = 'working'
    title = 'Работает'

    def lookups(self, request, model_admin):
        return (
            ('0', 'Нет'),
            ('1', 'Да')
        )

    def queryset(self, request, queryset):
        now = timezone.localtime(timezone.now())
        dayoff_query = Q(dayoff__start_date__lt=now, dayoff__end_date__gt=now)
        if self.value() == '1':
            queryset = queryset.exclude(dayoff_query)
        elif self.value() == '0':
            queryset = queryset.filter(dayoff_query)
        return queryset


class EmployeeManagerFilter(SimpleListFilter):
    parameter_name = 'is_manager'
    title = 'Управляющий'

    def lookups(self, request, model_admin):
        return (
            ('0', 'Нет'),
            ('1', 'Да')
        )

    def queryset(self, request, queryset):
        if self.value() == '1':
            queryset = queryset.exclude(managed_departments=None)
        elif self.value() == '0':
            queryset = queryset.filter(managed_departments=None)
        return queryset


@register(Employee, site=site)
class EmployeeAdmin(ModelAdmin):
    list_display = 'full_name', 'phone', 'departments_readable', 'joined_at', 'status'
    filter_horizontal = 'departments', 'managed_departments'
    list_filter = EmployeeManagerFilter, EmployeeWorkingFilter

    def status(self, obj):
        return not obj.dayoff_today
    status.short_description = 'Работает сегодня'
    status.boolean = True

    def departments_readable(self, obj):
        return ', '.join(k.title for k in obj.departments.all())
    departments_readable.short_description = 'Отделы'


@register(Department, site=site)
class DepartmentAdmin(ModelAdmin):
    form = DepartmentAdminForm


@register(Task, site=site)
class TaskAdmin(ModelAdmin):
    list_display = 'name', 'deadline'
    filter_horizontal = 'departments', 'employees'


@register(WaitingTaskReport, site=site)
class TaskReportAdmin(ModelAdmin):
    list_display = 'task_name', 'task_deadline', 'employee', 'text', \
                   'photo_link', 'checked', 'accepted', 'report_actions'
    readonly_fields = 'task_employee', 'report_actions'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.filter(task_employee__employee__departments__in=request.user.employee.managed_departments.all())
        return qs

    def photo_link(self, obj):
        if obj.photo:
            return mark_safe(f'<a href="{obj.photo}" target="_blank"><img width="200" src="{obj.photo}"></a>')
    photo_link.short_description = 'Фото'

    def report_actions(self, obj):
        return format_html(
            '<a class="button" href="{}">Утвердить</a>&nbsp;'
            '<a class="button" href="{}">Исправить</a>',
            reverse('admin:management_taskreport_confirm', args=[obj.pk]),
            reverse('admin:management_taskreport_correct', args=[obj.pk]),
        )
    report_actions.short_description = 'Действия'
    report_actions.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            re_path(
                '^(?P<report_id>.+)/confirm/$',
                self.admin_site.admin_view(self.process_confirm),
                name='management_taskreport_confirm',
            ),
            re_path(
                '^(?P<report_id>.+)/correct/$',
                self.admin_site.admin_view(self.process_correct),
                name='management_taskreport_correct',
            ),
        ]
        return custom_urls + urls

    def get_object(self, request, object_id, from_field=None):
        queryset = TaskReport.objects.all()
        model = queryset.model
        field = model._meta.pk if from_field is None else model._meta.get_field(from_field)
        try:
            object_id = field.to_python(object_id)
            return queryset.get(**{field.name: object_id})
        except (model.DoesNotExist, ValidationError, ValueError):
            return None

    def process_confirm(self, request, report_id):
        report = self.get_object(request, report_id)
        report.checked = True
        report.accepted = True
        report.save()
        return HttpResponseRedirect('/admin')

    def process_correct(self, request, report_id, *args, **kwargs):
        return self.process_action(
            request=request,
            report_id=report_id,
            action_form=CorrectTaskReport,
            action_title='Корректировка отчета',
        )

    def process_action(
            self,
            request,
            report_id,
            action_form,
            action_title
    ):
        report = self.get_object(request, report_id)
        if request.method != 'POST':
            form = action_form()
        else:
            form = action_form(request.POST, request.FILES)
            if form.is_valid():
                report.answer_file = request.FILES['file']
                form.save(report, request.user)
                self.message_user(request, 'Success')
                url = '/admin/'
                return HttpResponseRedirect(url)
        context = self.admin_site.each_context(request)
        context['opts'] = self.model._meta
        context['form'] = form
        context['report'] = report
        context['title'] = action_title
        return TemplateResponse(
            request,
            'admin/taskreport/report_action.html',
            context,
        )

    def task_name(self, obj): return obj.task_employee.task.name
    task_name.short_description = 'Задача'
    def task_deadline(self, obj): return obj.task_employee.task.deadline
    task_deadline.short_description = 'Срок выполнения'
    def task_departments(self, obj): return ', '.join(str(k) for k in obj.task_employee.task.departments.all())
    task_departments.short_description = 'Отделы'
    def employee(self, obj): return obj.task_employee.employee
    employee.short_description = 'Исполнитель'


@register(AcceptedTaskReport, site=site)
class AcceptedTaskReportAdmin(TaskReportAdmin):
    list_display = 'task_name', 'task_deadline', 'employee', 'text', \
                   'photo_link',


@register(DepartmentManager, site=site)
class DepartmentManagerAdmin(ModelAdmin):
    list_display = 'full_name', 'departments_readable'
    form = DepartmentManagerAdminForm

    def full_name(self, obj):
        return obj.employee.full_name

    full_name.short_description = 'Имя'

    def departments_readable(self, obj):
        return ', '.join(k.title for k in obj.departments.all())

    departments_readable.short_description = 'Отделы'


@register(DayOff, site=site)
class DayOffAdmin(ModelAdmin):
    list_display = 'employee', 'start_date', 'end_date', 'checked', 'confirmed', 'dayoff_actions'
    readonly_fields = 'dayoff_actions',
    list_filter = 'checked', 'confirmed'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            try:
                employee = request.user.employee
            except Employee.DoesNotExist:
                employee = None
            if employee:
                qs = qs.filter(employee__departments__in=employee.managed_departments.all())
        return qs

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<dayoff_id>/confirm/', self.process_confirm, name='management_dayoff_confirm'),
            path('<dayoff_id>/cancel/', self.process_cancel, name='management_dayoff_cancel'),
        ]
        return custom_urls + urls

    def process_confirm(self, request, dayoff_id):
        report = self.get_object(request, dayoff_id)
        report.checked = True
        report.confirmed = True
        report.save()
        return HttpResponseRedirect(reverse('admin:management_dayoff_changelist'))

    def process_cancel(self, request, dayoff_id):
        report = self.get_object(request, dayoff_id)
        report.checked = True
        report.confirmed = False
        report.save()
        return HttpResponseRedirect(reverse('admin:management_dayoff_changelist'))

    def dayoff_actions(self, obj):
        return format_html(
            '<a class="button" href="{}">Утвердить</a>&nbsp;'
            '<a class="button" href="{}">Отклонить</a>&nbsp;',
            reverse('admin:management_dayoff_confirm', args=[obj.pk]),
            reverse('admin:management_dayoff_cancel', args=[obj.pk]),
        )
    dayoff_actions.short_description = 'Действия'
