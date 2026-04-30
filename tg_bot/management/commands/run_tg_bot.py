# tg_bot/management/commands/run_tg_bot.py
from django.core.management.base import BaseCommand
from tg_bot.bot import run_bot

class Command(BaseCommand):
    help = "Start Telegram bot"
    def handle(self, *args, **opts):
        run_bot()

