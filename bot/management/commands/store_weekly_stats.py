from django.core.management.base import BaseCommand
from bot.cron import store_weekly_statistics


class Command(BaseCommand):
    help = 'Сохранить недельную статистику для всех аккаунтов'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Начинаем сохранение недельной статистики...'))
        
        try:
            store_weekly_statistics()
            self.stdout.write(self.style.SUCCESS('Недельная статистика успешно сохранена!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка при сохранении недельной статистики: {e}')) 