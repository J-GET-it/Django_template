import datetime
import logging
from django.conf import settings
from django.utils import timezone
from bot.models import User, AvitoAccount, AvitoAccountDailyStats
from bot.handlers.common import send_daily_report, send_weekly_report
from django.db.models import Q
from bot.services import get_access_token, get_user_balance_info, get_daily_statistics

logger = logging.getLogger(__name__)


def send_daily_reports_to_all_users():
    """Отправка ежедневных отчетов всем пользователям"""
    accounts = AvitoAccount.objects.filter(
        client_id__isnull=False, 
        client_secret__isnull=False
    ).exclude(client_id="none")
    
    logger.info(f'Найдено аккаунтов для ежедневных отчетов: {accounts.count()}')
    
    for account in accounts:
        try:
            # Отправляем дневной отчет в указанный telegram_id
            if account.daily_report_tg_id:
                logger.info(f"Отправка ежедневного отчета для аккаунта {account.name} на ID: {account.daily_report_tg_id}")
                send_daily_report(account.daily_report_tg_id, account.id)
            else:
                logger.info(f"Аккаунт {account.name} не имеет указанного получателя ежедневных отчетов")
        except Exception as e:
            logger.error(f"Ошибка при отправке ежедневного отчета для аккаунта {account.name}: {e}")


def send_weekly_reports_to_all_users():
    """Отправка еженедельных отчетов всем пользователям"""
    accounts = AvitoAccount.objects.filter(
        client_id__isnull=False, 
        client_secret__isnull=False
    ).exclude(client_id="none")
    
    logger.info(f'Найдено аккаунтов для еженедельных отчетов: {accounts.count()}')
    
    for account in accounts:
        try:
            # Отправляем недельный отчет
            if account.weekly_report_tg_id:
                logger.info(f"Отправка еженедельного отчета для аккаунта {account.name} на ID: {account.weekly_report_tg_id}")
                send_weekly_report(account.weekly_report_tg_id, account.id)
            else:
                logger.info(f"Аккаунт {account.name} не имеет указанного получателя еженедельных отчетов")
        except Exception as e:
            logger.error(f"Ошибка при отправке еженедельного отчета для аккаунта {account.name}: {e}")


def track_user_expenses():
    """Отслеживание расходов аккаунтов на основе изменения баланса"""
    accounts = AvitoAccount.objects.filter(
        client_id__isnull=False, 
        client_secret__isnull=False
    ).exclude(client_id="none")
    
    current_time = datetime.datetime.now()
    
    for account in accounts:
        try:
            # Получаем токен доступа
            access_token = get_access_token(account.client_id, account.client_secret)
            if not access_token:
                logger.error(f"Не удалось получить токен доступа для аккаунта {account.name}")
                continue
                
            # Получаем текущий баланс аккаунта
            balance_info = get_user_balance_info(access_token)
            
            # Используем сумму реального баланса, бонусов и авансовых платежей
            current_balance = balance_info["balance_real"] + balance_info["balance_bonus"] + balance_info["advance"]
            
            # Если это первая проверка баланса
            if account.last_balance_check is None:
                account.last_balance = current_balance
                account.last_balance_check = current_time
                account.save()
                logger.info(f"Инициализация баланса аккаунта {account.name}: {current_balance}")
                continue
            
            # Проверяем, уменьшился ли баланс (произошел расход)
            if current_balance < account.last_balance:
                # Рассчитываем сумму расхода
                expense_amount = account.last_balance - current_balance
                
                # Обновляем дневной расход
                account.daily_expense += expense_amount
                
                # Обновляем недельный расход
                account.weekly_expense += expense_amount
                
                logger.info(f"Зафиксирован расход для аккаунта {account.name}: {expense_amount} р. "
                           f"Дневной расход: {account.daily_expense} р., Недельный расход: {account.weekly_expense} р.")
            
            # Обновляем значение последнего баланса и времени проверки
            account.last_balance = current_balance
            account.last_balance_check = current_time
            account.save()
            
        except Exception as e:
            logger.error(f"Ошибка при отслеживании расходов аккаунта {account.name}: {e}")


def reset_daily_expenses():
    """Сброс дневных расходов в начале нового дня"""
    try:
        # Сбрасываем дневной расход для всех аккаунтов
        accounts = AvitoAccount.objects.all()
        for account in accounts:
            if account.daily_expense > 0:
                logger.info(f"Сброс дневного расхода для аккаунта {account.name}: {account.daily_expense} р.")
                account.daily_expense = 0
                account.save()
    except Exception as e:
        logger.error(f"Ошибка при сбросе дневных расходов: {e}")


def reset_weekly_expenses():
    """Сброс недельных расходов в начале новой недели"""
    try:
        # Сбрасываем недельный расход для всех аккаунтов
        accounts = AvitoAccount.objects.all()
        for account in accounts:
            if account.weekly_expense > 0:
                logger.info(f"Сброс недельного расхода для аккаунта {account.name}: {account.weekly_expense} р.")
                account.weekly_expense = 0
                account.save()
    except Exception as e:
        logger.error(f"Ошибка при сбросе недельных расходов: {e}")


def store_daily_statistics():
    """Сохранение ежедневной статистики для всех аккаунтов"""
    try:
        # Получаем все аккаунты с настроенным API
        accounts = AvitoAccount.objects.filter(
            ~Q(client_id='none') & ~Q(client_secret='none')
        )
        
        if not accounts.exists():
            logger.info("Нет настроенных аккаунтов для сохранения статистики")
            return
        
        # Рассчитываем вчерашнюю дату
        yesterday = timezone.now().date() - timezone.timedelta(days=1)
        
        for account in accounts:
            try:
                # Получаем статистику за вчерашний день
                client_id = account.client_id
                client_secret = account.client_secret
                daily_stats = get_daily_statistics(client_id, client_secret, str(yesterday))
                
                if not daily_stats:
                    logger.warning(f"Не удалось получить статистику для аккаунта {account.name}")
                    continue
                
                # Создаем запись в базе данных
                stats = AvitoAccountDailyStats(
                    avito_account=account,
                    date=yesterday,
                    total_calls=daily_stats['calls']['total'],
                    answered_calls=daily_stats['calls']['answered'],
                    missed_calls=daily_stats['calls']['missed'],
                    total_chats=daily_stats['chats']['total'],
                    new_chats=daily_stats['chats']['new'],
                    phones_received=daily_stats['phones_received'],
                    rating=daily_stats['rating'],
                    total_reviews=daily_stats['reviews']['total'],
                    daily_reviews=daily_stats['reviews']['today'],
                    total_items=daily_stats['items']['total'],
                    xl_promotion_count=daily_stats['items']['with_xl_promotion'],
                    views=daily_stats['statistics']['views'],
                    contacts=daily_stats['statistics']['contacts'],
                    favorites=daily_stats['statistics']['favorites'],
                    balance_real=daily_stats['balance_real'],
                    balance_bonus=daily_stats['balance_bonus'],
                    advance=daily_stats['advance'],
                    daily_expense=account.daily_expense  # Берем расход из аккаунта
                )
                
                stats.save()
                logger.info(f"Сохранена статистика для аккаунта {account.name} за {yesterday}")
                
            except Exception as e:
                logger.error(f"Ошибка при сохранении статистики для аккаунта {account.name}: {e}")
        
        logger.info("Сохранение ежедневной статистики завершено")
    except Exception as e:
        logger.error(f"Ошибка при сохранении ежедневной статистики: {e}")


def clean_old_statistics():
    """Удаление статистики старше 30 дней"""
    try:
        threshold_date = timezone.now().date() - datetime.timedelta(days=30)
        old_stats = AvitoAccountDailyStats.objects.filter(date__lt=threshold_date)
        count = old_stats.count()
        
        if count > 0:
            old_stats.delete()
            logger.info(f"Удалено {count} записей статистики старше {threshold_date}")
        else:
            logger.info(f"Нет записей статистики старше {threshold_date} для удаления")
            
    except Exception as e:
        logger.error(f"Ошибка при удалении старой статистики: {e}")


def ensure_daily_stats_exists():
    """
    Проверяет наличие записей о статистике за сегодня и вчера в базе данных.
    Если записей нет, запускает процесс их создания.
    """
    try:
        today = timezone.now().date()
        yesterday = today - datetime.timedelta(days=1)
        
        # Получаем все активные аккаунты
        accounts = AvitoAccount.objects.filter(
            client_id__isnull=False, 
            client_secret__isnull=False
        ).exclude(client_id="none")
        
        logger.info(f"Проверка наличия статистики за {yesterday} и {today} для {accounts.count()} аккаунтов")
        
        for account in accounts:
            try:
                # Проверяем наличие статистики за вчера
                yesterday_stats_exists = AvitoAccountDailyStats.objects.filter(
                    avito_account=account,
                    date=yesterday
                ).exists()
                
                if not yesterday_stats_exists:
                    logger.info(f"Создаем статистику за вчера ({yesterday}) для аккаунта {account.name}")
                    store_account_daily_stats(account, yesterday)
                
                # Проверяем наличие статистики за сегодня
                today_stats_exists = AvitoAccountDailyStats.objects.filter(
                    avito_account=account,
                    date=today
                ).exists()
                
                if not today_stats_exists:
                    logger.info(f"Создаем статистику за сегодня ({today}) для аккаунта {account.name}")
                    store_account_daily_stats(account, today)
                    
            except Exception as e:
                logger.error(f"Ошибка при проверке/создании статистики для аккаунта {account.name}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка в ensure_daily_stats_exists: {e}")


def store_account_daily_stats(account, date):
    """Сохраняет статистику по аккаунту за указанную дату"""
    try:
        # Проверяем, существует ли у нас уже запись за эту дату
        if AvitoAccountDailyStats.objects.filter(avito_account=account, date=date).exists():
            logger.info(f"Статистика для аккаунта {account.name} за {date} уже существует")
            return
        
        # Получаем статистику за указанный день
        client_id = account.client_id
        client_secret = account.client_secret
        daily_stats = get_daily_statistics(client_id, client_secret, str(date))
        
        if not daily_stats:
            logger.warning(f"Не удалось получить статистику для аккаунта {account.name} за {date}")
            return
            
        # Определяем, является ли день сегодняшним
        is_today = date == timezone.now().date()
        
        # Создаем запись в базе данных
        stats, created = AvitoAccountDailyStats.objects.get_or_create(
            avito_account=account,
            date=date,
            defaults={
                'total_calls': daily_stats['calls']['total'],
                'answered_calls': daily_stats['calls']['answered'],
                'missed_calls': daily_stats['calls']['missed'],
                'total_chats': daily_stats['chats']['total'],
                'new_chats': daily_stats['chats']['new'],
                'phones_received': daily_stats['phones_received'],
                'rating': daily_stats['rating'],
                'total_reviews': daily_stats['reviews']['total'],
                'daily_reviews': daily_stats['reviews']['today'],
                'total_items': daily_stats['items']['total'],
                'xl_promotion_count': daily_stats['items']['with_xl_promotion'],
                'views': daily_stats['statistics']['views'],
                'contacts': daily_stats['statistics']['contacts'],
                'favorites': daily_stats['statistics']['favorites'],
                'balance_real': daily_stats['balance_real'],
                'balance_bonus': daily_stats['balance_bonus'],
                'advance': daily_stats['advance'],
                'daily_expense': account.daily_expense if is_today else 0  # Для сегодняшнего дня берем текущий расход
            }
        )
        
        logger.info(f"{'Создана' if created else 'Обновлена'} статистика для аккаунта {account.name} за {date}")
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении статистики для аккаунта {account.name} за {date}: {e}")


# Функции для запуска через cron
def daily_task():
    """Задача для ежедневного запуска через cron"""
    # Сначала проверяем наличие данных за текущий и предыдущий день
    ensure_daily_stats_exists()
    
    # Сохраняем статистику за предыдущий день
    store_daily_statistics()
    
    # Проверяем аномалии и отправляем уведомления
    try:
        from bot.send_notification import check_anomalies
        check_anomalies()
    except Exception as e:
        logger.error(f"Ошибка при проверке аномалий: {e}")
    
    # Затем отправляем отчеты
    send_daily_reports_to_all_users()
    
    # Сбрасываем дневные расходы
    reset_daily_expenses()
    
    # Удаляем старую статистику
    clean_old_statistics()


def weekly_task():
    """Задача для еженедельного запуска через cron"""
    send_weekly_reports_to_all_users()
    reset_weekly_expenses()


def populate_historical_data(days=30):
    """
    Заполняет базу данных историческими данными за указанное количество дней.
    Эту функцию можно запустить один раз для наполнения БД историческими данными.
    
    Args:
        days: Количество дней для заполнения (по умолчанию 30)
    """
    try:
        today = timezone.now().date()
        
        # Получаем все активные аккаунты
        accounts = AvitoAccount.objects.filter(
            client_id__isnull=False, 
            client_secret__isnull=False
        ).exclude(client_id="none")
        
        logger.info(f"Начало заполнения исторических данных за {days} дней для {accounts.count()} аккаунтов")
        
        for account in accounts:
            try:
                logger.info(f"Заполнение данных для аккаунта {account.name}")
                
                # Проходим по каждому дню
                for day_offset in range(days, 0, -1):
                    date = today - datetime.timedelta(days=day_offset)
                    
                    # Проверяем, есть ли уже запись за этот день
                    stat_exists = AvitoAccountDailyStats.objects.filter(
                        avito_account=account,
                        date=date
                    ).exists()
                    
                    if stat_exists:
                        logger.info(f"Запись для {date} уже существует, пропускаем")
                        continue
                    
                    logger.info(f"Создание записи за {date} для аккаунта {account.name}")
                    
                    # Создаем запись
                    store_account_daily_stats(account, date)
                    
                    # Делаем небольшую паузу, чтобы не перегружать API
                    import time
                    time.sleep(1)
                
                logger.info(f"Заполнение данных для аккаунта {account.name} завершено")
                
            except Exception as e:
                logger.error(f"Ошибка при заполнении данных для аккаунта {account.name}: {e}")
        
        logger.info(f"Заполнение исторических данных завершено")
        
    except Exception as e:
        logger.error(f"Ошибка в populate_historical_data: {e}")


def minutely_task():
    """Задача для запуска каждую минуту через cron"""
    track_user_expenses()

