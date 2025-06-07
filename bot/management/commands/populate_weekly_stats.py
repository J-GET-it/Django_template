from django.core.management.base import BaseCommand
from django.utils import timezone
from bot.models import AvitoAccount, AvitoAccountWeeklyStats
from bot.services import get_weekly_statistics
import datetime
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Заполнить недельную статистику за указанное количество недель'

    def add_arguments(self, parser):
        parser.add_argument(
            '--weeks',
            type=int,
            default=4,
            help='Количество недель для заполнения (по умолчанию 4)'
        )

    def handle(self, *args, **options):
        weeks = options['weeks']
        self.stdout.write(self.style.SUCCESS(f'Начинаем заполнение недельной статистики за {weeks} недель...'))
        
        try:
            # Получаем все аккаунты с настроенным API
            accounts = AvitoAccount.objects.filter(
                client_id__isnull=False,
                client_secret__isnull=False
            ).exclude(client_id="none")
            
            if not accounts.exists():
                self.stdout.write(self.style.WARNING('Нет настроенных аккаунтов'))
                return
            
            today = timezone.now().date()
            
            for account in accounts:
                self.stdout.write(f'Обрабатываем аккаунт: {account.name}')
                
                # Проходим по каждой неделе
                for week_offset in range(weeks, 0, -1):
                    # Рассчитываем даты недели
                    days_since_monday = today.weekday()
                    current_week_start = today - datetime.timedelta(days=days_since_monday)
                    week_start = current_week_start - datetime.timedelta(weeks=week_offset)
                    week_end = week_start + datetime.timedelta(days=6)
                    
                    # Проверяем, есть ли уже запись за эту неделю
                    existing_stats = AvitoAccountWeeklyStats.objects.filter(
                        avito_account=account,
                        week_start_date=week_start
                    ).first()
                    
                    if existing_stats:
                        self.stdout.write(f'  Неделя {week_start} - {week_end}: уже существует')
                        continue
                    
                    try:
                        # Получаем недельную статистику через API
                        weekly_stats = get_weekly_statistics(account.client_id, account.client_secret)
                        
                        if not weekly_stats:
                            self.stdout.write(self.style.WARNING(f'  Неделя {week_start} - {week_end}: не удалось получить данные'))
                            continue
                        
                        # Создаем запись
                        stats = AvitoAccountWeeklyStats(
                            avito_account=account,
                            week_start_date=week_start,
                            week_end_date=week_end,
                            period=f"{week_start} - {week_end}",
                            total_calls=weekly_stats['calls']['total'],
                            answered_calls=weekly_stats['calls']['answered'],
                            missed_calls=weekly_stats['calls']['missed'],
                            total_chats=weekly_stats['chats']['total'],
                            new_chats=weekly_stats['chats'].get('new', 0),
                            phones_received=weekly_stats['phones_received'],
                            rating=weekly_stats['rating'],
                            total_reviews=weekly_stats['reviews']['total'],
                            weekly_reviews=weekly_stats['reviews']['weekly'],
                            total_items=weekly_stats['items']['total'],
                            xl_promotion_count=weekly_stats['items']['with_xl_promotion'],
                            views=weekly_stats['statistics']['views'],
                            contacts=weekly_stats['statistics']['contacts'],
                            favorites=weekly_stats['statistics']['favorites'],
                            balance_real=weekly_stats['balance_real'],
                            balance_bonus=weekly_stats['balance_bonus'],
                            advance=weekly_stats['advance'],
                            cpa_balance=weekly_stats.get('cpa_balance', 0),
                            weekly_expense=account.weekly_expense
                        )
                        
                        # Сохраняем детализацию расходов
                        if 'expenses' in weekly_stats and 'details' in weekly_stats['expenses']:
                            stats.set_expenses_details(weekly_stats['expenses']['details'])
                        
                        stats.save()
                        self.stdout.write(self.style.SUCCESS(f'  Неделя {week_start} - {week_end}: сохранено'))
                        
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'  Неделя {week_start} - {week_end}: ошибка - {e}'))
                        
                    # Небольшая пауза между запросами
                    import time
                    time.sleep(1)
            
            self.stdout.write(self.style.SUCCESS('Заполнение недельной статистики завершено!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка при заполнении недельной статистики: {e}')) 