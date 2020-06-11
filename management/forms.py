from django import forms
from viber import viber
from viberbot.api.messages import TextMessage, FileMessage
from django.conf import settings
from .models import Employee, Department, TaskReport, TaskEmployee
from .utils import get_task_messages


class DepartmentAdminForm(forms.ModelForm):
    employees = forms.ModelMultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(),
        label='Сотрудники',
        queryset=Employee.objects.order_by('full_name'),
        required=False
    )
    report_managers = forms.ModelMultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(),
        label='Принимающие отчеты',
        help_text='Если пусто, то отчеты принимают все менеджеры',
        queryset=Employee.objects.all(),
        required=False
    )

    def __init__(self, *args, **kwargs):
        department = kwargs.get('instance')
        super(DepartmentAdminForm, self).__init__(*args, **kwargs)
        if department:
            self.fields['report_managers'].queryset = Employee.objects.filter(
                managed_departments__exact=department)
            self.fields['employees'].initial = Employee.objects.filter(
                departments__exact=department).values_list('id', flat=True)


class DepartmentManagerAdminForm(forms.ModelForm):
    departments = forms.ModelMultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(),
        label='Отделы',
        queryset=Department.objects.order_by('title')
    )

    def __init__(self, *args, **kwargs):
        department_manager = kwargs.get('instance')
        super(DepartmentManagerAdminForm, self).__init__(*args, **kwargs)
        if department_manager:
            self.fields['departments'].initial = \
                department_manager.employee.departments.all().values_list('id', flat=True)


class ActionForm(forms.Form):
    def form_action(self, account, user):
        raise NotImplementedError()

    def save(self, instance, user):
        instance, action = self.form_action(instance, user)
        return instance, action


class CorrectTaskReport(ActionForm):
    text = forms.CharField(
        widget=forms.Textarea,
        label='Текст',
        required=False
    )
    file = forms.FileField(
        label='Файл',
        required=False
    )

    def form_action(self, instance: TaskReport, user):
        instance.answer_text = self.cleaned_data['text']
        instance.checked = True
        instance.accepted = False
        instance.save()

        TaskEmployee.objects.filter(task=instance.task_employee.task, employee=instance.task_employee.employee).update(finished=True)
        TaskEmployee.objects.create(task=instance.task_employee.task, employee=instance.task_employee.employee)
        messages = get_task_messages(instance.task_employee.task)
        if instance.answer_text:
            messages.append(TextMessage(text=instance.answer_text))
        if instance.answer_file:
            messages.append(FileMessage(media=settings.VIBER_MEDIA_HOST + instance.answer_file.url, size=instance.answer_file.size, file_name=instance.answer_file.name))
        viber.send_messages(instance.task_employee.employee.bot_user.chat_id, messages)
        return instance, user
