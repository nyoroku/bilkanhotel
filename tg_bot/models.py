# tg_bot/models.py
from django.db import models
from accounts.models import User   # your custom model

class TelegramUser(models.Model):
    user      = models.OneToOneField(User, on_delete=models.CASCADE)
    chat_id   = models.BigIntegerField(unique=True)
    first_name= models.CharField(max_length=128, blank=True)
    username  = models.CharField(max_length=128, blank=True)

