from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from management.models import BotUser
from viber import hook


@csrf_exempt
def viber_hook(request):
    return hook(request)

