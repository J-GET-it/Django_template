from bot import bot
from bot.models import User, AvitoAccount, UserAvitoAccount, AvitoAccountDailyStats, Settings
from bot.keyboards import main_markup
from bot.texts import MAIN_TEXT
from bot.services import get_daily_statistics, get_weekly_statistics
import telebot
from django.db import models
import datetime
from django.utils import timezone

import logging

logger = logging.getLogger(__name__)

def start(message):
    """Обработчик команды /start"""
    from bot.handlers.registration import start_registration
    start_registration(message)

def menu_m(message):
    """Главное меню"""
    chat_id = message.chat.id if hasattr(message, 'chat') else message.from_user.id
    bot.send_message(
        chat_id=chat_id,
        text=MAIN_TEXT,
        reply_markup=main_markup
    )

def format_expenses_message(expenses):
    """Форматирует сообщение о расходах"""
    if not expenses:
        return "0.00 ₽"
        
    # Проверяем правильность структуры
    if not isinstance(expenses, dict):
        return "0.00 ₽"
        
    total = expenses.get('total', 0)
    details = expenses.get('details', {})
    
    if total <= 0:
        return "0.00 ₽"
    
    message = f"{total:.2f} ₽\n"
    
    # Добавляем детализацию расходов, если они есть
    if details:
        message += f"📋 *Детализация расходов:*\n"
        
        # Сортируем по убыванию суммы
        sorted_details = sorted(
            details.items(), 
            key=lambda x: x[1]['amount'], 
            reverse=True
        )
        
        for service, service_details in sorted_details:
            amount = service_details.get('amount', 0)
            count = service_details.get('count', 1)
            items = service_details.get('items', [])
            
            # Количество объявлений, если есть
            items_count = len(items) if items else 0
            items_suffix = ""
            if items_count > 0:
                items_suffix = f" ({items_count} объявл.)"
            
            message += f"   • {service}{items_suffix}: {amount:.2f} ₽ ({count} опер.)\n"
    
    return message

def select_avito_account(chat_id, user_id, callback_prefix):
    """Отображает выбор аккаунтов Авито для пользователя"""
    try:
        # Детальное логирование для отладки
        logger.info(f"ОТЛАДКА: select_avito_account вызван для пользователя {user_id}, chat_id: {chat_id}")
        
        # Получаем пользователя
        user = User.objects.filter(telegram_id=user_id).first()
        
        logger.info(f"ОТЛАДКА: Найден пользователь: {user}")
        
        if not user:
            bot.send_message(chat_id, "❌ Вы не зарегистрированы. Используйте /start для регистрации.")
            return
        
        # Получаем все аккаунты Авито в системе
        accounts = AvitoAccount.objects.filter(
            client_id__isnull=False,
            client_secret__isnull=False
        ).exclude(client_id="none").distinct()
        
        logger.info(f"ОТЛАДКА: Найдено аккаунтов Авито: {accounts.count()}")
        
        if not accounts.exists():
            bot.send_message(chat_id, "❌ В системе нет зарегистрированных аккаунтов Авито")
            logger.error(f"Нет аккаунтов в системе")
            return
            
        if accounts.count() == 1:
            # Если только один аккаунт, сразу используем его
            account_id = accounts.first().id
            logger.info(f"ОТЛАДКА: Найден один аккаунт: {account_id}, используем его напрямую")
            if callback_prefix == "daily_report":
                daily_report_for_account(chat_id, account_id)
            else:
                weekly_report_for_account(chat_id, account_id)
            return
            
        # Создаем клавиатуру для выбора аккаунта
        markup = telebot.types.InlineKeyboardMarkup()
        for account in accounts:
            button = telebot.types.InlineKeyboardButton(
                text=account.name,
                callback_data=f"{callback_prefix}_{account.id}"
            )
            markup.add(button)
            logger.info(f"ОТЛАДКА: Добавлена кнопка для аккаунта {account.id}: {account.name}, callback_data: {callback_prefix}_{account.id}")
            
        bot.send_message(
            chat_id=chat_id,
            text="Выберите аккаунт Авито для отчета:",
            reply_markup=markup
        )
    except User.DoesNotExist:
        bot.send_message(chat_id, "❌ Вы не зарегистрированы. Используйте /start для регистрации.")
    except Exception as e:
        logger.error(f"Ошибка при выборе аккаунта: {e}")
        logger.exception("Полный стек-трейс ошибки:")
        bot.send_message(chat_id, f"❌ Произошла ошибка: {str(e)}")

def daily_report(call):
    """Обработчик для получения дневного отчета"""
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    logger.info(f"ОТЛАДКА: daily_report вызван, user_id: {user_id}, chat_id: {chat_id}")
    
    # Проверяем, есть ли в callback_data идентификатор аккаунта
    parts = call.data.split("_")
    if len(parts) > 2 and parts[0] == "daily" and parts[1] == "report":
        # Если формат daily_report_ID, получаем отчет для конкретного аккаунта
        try:
            account_id = int(parts[2])
            daily_report_for_account(chat_id, account_id)
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при обработке callback_data: {e}")
            bot.send_message(chat_id, "❌ Ошибка при обработке запроса. Пожалуйста, попробуйте снова.")
    else:
        # Иначе предлагаем выбрать аккаунт
        select_avito_account(chat_id, user_id, "daily_report")

def weekly_report(call):
    """Обработчик для получения недельного отчета"""
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    logger.info(f"ОТЛАДКА: weekly_report вызван, user_id: {user_id}, chat_id: {chat_id}")
    
    # Проверяем, есть ли в callback_data идентификатор аккаунта
    parts = call.data.split("_")
    if len(parts) > 2 and parts[0] == "weekly" and parts[1] == "report":
        # Если формат weekly_report_ID, получаем отчет для конкретного аккаунта
        try:
            account_id = int(parts[2])
            weekly_report_for_account(chat_id, account_id)
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при обработке callback_data: {e}")
            bot.send_message(chat_id, "❌ Ошибка при обработке запроса. Пожалуйста, попробуйте снова.")
    else:
        # Иначе предлагаем выбрать аккаунт
        select_avito_account(chat_id, user_id, "weekly_report")

def calculate_percentage_change(current, previous):
    """Рассчитывает процентное изменение между текущим и предыдущим значением"""
    if previous == 0:
        return 100 if current > 0 else 0
    return ((current - previous) / previous) * 100

def format_percentage_change(percentage, show_positive=True):
    """Форматирует процентное изменение для вывода в сообщении"""
    if percentage > 0:
        return f"⬆️ +{percentage:.1f}%" if show_positive else f"⬆️ {percentage:.1f}%"
    elif percentage < 0:
        return f"⬇️ {percentage:.1f}%"
    else:
        return "⏺ 0%"

def get_previous_day_stats(account_id, current_date):
    """Получает статистику за предыдущий день"""
    try:
        # Получаем дату предыдущего дня
        previous_date = current_date - datetime.timedelta(days=1)
        # Ищем статистику за предыдущий день
        previous_stats = AvitoAccountDailyStats.objects.filter(
            avito_account_id=account_id,
            date=previous_date
        ).first()
        return previous_stats
    except Exception as e:
        logger.error(f"Ошибка при получении статистики за предыдущий день: {e}")
        return None

def get_previous_week_stats(account_id, current_date):
    """Получает статистику за предыдущую неделю (суммарно)"""
    try:
        # Получаем начало предыдущей недели
        week_start = current_date - datetime.timedelta(days=14)
        week_end = current_date - datetime.timedelta(days=7)
        
        # Получаем все записи за предыдущую неделю
        previous_week_stats = AvitoAccountDailyStats.objects.filter(
            avito_account_id=account_id,
            date__gte=week_start,
            date__lt=week_end
        )
        
        # Если нет данных, возвращаем None
        if not previous_week_stats.exists():
            return None
            
        # Суммируем данные
        total_calls = sum(stats.total_calls for stats in previous_week_stats)
        answered_calls = sum(stats.answered_calls for stats in previous_week_stats)
        missed_calls = sum(stats.missed_calls for stats in previous_week_stats)
        total_chats = sum(stats.total_chats for stats in previous_week_stats)
        new_chats = sum(stats.new_chats for stats in previous_week_stats)
        phones_received = sum(stats.phones_received for stats in previous_week_stats)
        views = sum(stats.views for stats in previous_week_stats)
        contacts = sum(stats.contacts for stats in previous_week_stats)
        favorites = sum(stats.favorites for stats in previous_week_stats)
        daily_reviews = sum(stats.daily_reviews for stats in previous_week_stats)
        daily_expense = sum(stats.daily_expense for stats in previous_week_stats)
        
        # Создаем объект с суммарными данными
        class WeeklySummary:
            def __init__(self):
                self.total_calls = total_calls
                self.answered_calls = answered_calls
                self.missed_calls = missed_calls
                self.total_chats = total_chats
                self.new_chats = new_chats
                self.phones_received = phones_received
                self.views = views
                self.contacts = contacts
                self.favorites = favorites
                self.daily_reviews = daily_reviews
                self.daily_expense = daily_expense
                
        return WeeklySummary()
    except Exception as e:
        logger.error(f"Ошибка при получении статистики за предыдущую неделю: {e}")
        return None

def daily_report_for_account(chat_id, account_id):
    """Отправка дневного отчета для конкретного аккаунта"""
    # Отправляем сообщение о загрузке и сохраняем его ID
    loading_message = bot.send_message(chat_id, "⏳ Получаем данные из API Авито...")
    
    try:
        account = AvitoAccount.objects.get(id=account_id)
        client_id = account.client_id
        client_secret = account.client_secret
        response = get_daily_statistics(client_id, client_secret)
        
        # Удаляем сообщение о загрузке после получения данных
        bot.delete_message(chat_id, loading_message.message_id)
        
        # Получаем дату текущего отчета в формате datetime.date
        today_date = datetime.datetime.strptime(response['date'], '%Y-%m-%d').date()
        
        # Получаем статистику за предыдущий день
        previous_stats = get_previous_day_stats(account_id, today_date)
        
        # Проверяем текущий формат отчета
        report_format = Settings.get_value("report_format", "new")
        
        # Используем соответствующий формат отчета
        if report_format == "new":
            message_text = format_daily_report_new(account, response, previous_stats)
        else:
            message_text = format_daily_report_standard(account, response, previous_stats)
        
        bot.send_message(chat_id, message_text, parse_mode="Markdown")
        
    except AvitoAccount.DoesNotExist:
        # Удаляем сообщение о загрузке в случае ошибки
        bot.delete_message(chat_id, loading_message.message_id)
        bot.send_message(chat_id, "❌ Ошибка: аккаунт не найден")
    except Exception as e:
        # Удаляем сообщение о загрузке в случае ошибки
        try:
            bot.delete_message(chat_id, loading_message.message_id)
        except:
            pass
        logger.error(f"Ошибка при получении дневного отчета: {e}")
        bot.send_message(chat_id, f"❌ Произошла ошибка: {str(e)}")

def weekly_report_for_account(chat_id, account_id):
    """Отправка недельного отчета для конкретного аккаунта"""
    # Отправляем сообщение о загрузке и сохраняем его ID
    loading_message = bot.send_message(chat_id, "⏳ Получаем данные из API Авито...")
    
    try:
        account = AvitoAccount.objects.get(id=account_id)
        client_id = account.client_id
        client_secret = account.client_secret
        response = get_weekly_statistics(client_id, client_secret)
        
        # Удаляем сообщение о загрузке после получения данных
        bot.delete_message(chat_id, loading_message.message_id)
        
        # Получаем текущую дату для поиска данных предыдущей недели
        current_date = timezone.now().date()
        
        # Получаем статистику за предыдущую неделю
        previous_week_stats = get_previous_week_stats(account_id, current_date)
        
        # Проверяем текущий формат отчета
        report_format = Settings.get_value("report_format", "new")
        
        # Используем соответствующий формат отчета
        if report_format == "new":
            message_text = format_weekly_report_new(account, response, previous_week_stats)
        else:
            # Формируем читаемое сообщение для пользователя в стандартном формате
            message_text = f"📈 *Статистика за период: {response['period']} - {account.name}*\n\n"
            
            # Звонки
            message_text += f"📞 *Звонки:*\n"
            message_text += f"   • Всего: {response['calls']['total']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['calls']['total'], previous_week_stats.total_calls)
                message_text += f" {format_percentage_change(percentage)}\n"
            else:
                message_text += "\n"
                
            message_text += f"   • Отвечено: {response['calls']['answered']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['calls']['answered'], previous_week_stats.answered_calls)
                message_text += f" {format_percentage_change(percentage)}\n"
            else:
                message_text += "\n"
                
            message_text += f"   • Пропущено: {response['calls']['missed']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['calls']['missed'], previous_week_stats.missed_calls)
                message_text += f" {format_percentage_change(percentage)}\n\n"
            else:
                message_text += "\n\n"
            
            # Сообщения
            message_text += f"💬 *Сообщения:*\n"
            message_text += f"   • Новых за неделю: {response['chats']['total']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['chats']['total'], previous_week_stats.total_chats)
                message_text += f" {format_percentage_change(percentage)}\n"
            else:
                message_text += "\n"
                
            message_text += f"📱 *Показов телефона:* {response['phones_received']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['phones_received'], previous_week_stats.phones_received)
                message_text += f" {format_percentage_change(percentage)}\n\n"
            else:
                message_text += "\n\n"
            
            # Рейтинг и отзывы
            message_text += f"⭐ *Рейтинг:* {response['rating']}\n"
            message_text += f"👍 *Отзывы:*\n"
            message_text += f"   • Всего: {response['reviews']['total']}\n"
            message_text += f"   • За неделю: {response['reviews']['weekly']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['reviews']['weekly'], previous_week_stats.daily_reviews)
                message_text += f" {format_percentage_change(percentage)}\n\n"
            else:
                message_text += "\n\n"
            
            # Объявления
            message_text += f"📝 *Объявления:*\n"
            message_text += f"   • Всего: {response['items']['total']}\n"
            message_text += f"   • С XL продвижением: {response['items']['with_xl_promotion']}\n\n"
            
            # Статистика просмотров
            message_text += f"👁 *Просмотры:* {response['statistics']['views']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['statistics']['views'], previous_week_stats.views)
                message_text += f" {format_percentage_change(percentage)}\n"
            else:
                message_text += "\n"
                
            message_text += f"📲 *Контакты:* {response['statistics']['contacts']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['statistics']['contacts'], previous_week_stats.contacts)
                message_text += f" {format_percentage_change(percentage)}\n"
            else:
                message_text += "\n"
                
            message_text += f"❤️ *В избранном:* {response['statistics']['favorites']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['statistics']['favorites'], previous_week_stats.favorites)
                message_text += f" {format_percentage_change(percentage)}\n\n"
            else:
                message_text += "\n\n"
            
            # Финансы
            message_text += f"💰 *Финансы:*\n"
            message_text += f"   • Реальный баланс: {response['balance_real']} ₽\n"
            message_text += f"   • Бонусы: {response['balance_bonus']} ₽\n"
            message_text += f"   • Аванс: {response['advance']} ₽\n\n"
            
            message_text += f"💸 *Расходы за неделю:* "
            
            # Добавляем расходы и детализацию
            expenses_message = format_expenses_message(response.get('expenses', {}))
            message_text += expenses_message
            
            if previous_week_stats and previous_week_stats.daily_expense > 0:
                percentage = calculate_percentage_change(account.weekly_expense, previous_week_stats.daily_expense)
                message_text += f"\n*Изменение расходов: {format_percentage_change(percentage)}*"
        
        bot.send_message(chat_id, message_text, parse_mode="Markdown")
        
    except AvitoAccount.DoesNotExist:
        # Удаляем сообщение о загрузке в случае ошибки
        bot.delete_message(chat_id, loading_message.message_id)
        bot.send_message(chat_id, "❌ Ошибка: аккаунт не найден")
    except Exception as e:
        # Удаляем сообщение о загрузке в случае ошибки
        try:
            bot.delete_message(chat_id, loading_message.message_id)
        except:
            pass
        logger.error(f"Ошибка при получении недельного отчета: {e}")
        bot.send_message(chat_id, f"❌ Произошла ошибка: {str(e)}")

def send_weekly_report(telegram_id, account_id):
    """Отправка недельного отчета по ID в Telegram и ID аккаунта Авито"""
    try:
        account = AvitoAccount.objects.get(id=account_id)
        client_id = account.client_id
        client_secret = account.client_secret
        response = get_weekly_statistics(client_id, client_secret)
        
        # Получаем текущую дату для поиска данных предыдущей недели
        current_date = timezone.now().date()
        
        # Получаем статистику за предыдущую неделю
        previous_week_stats = get_previous_week_stats(account_id, current_date)
        
        # Проверяем текущий формат отчета
        report_format = Settings.get_value("report_format", "new")
        
        # Используем соответствующий формат отчета
        if report_format == "new":
            message_text = format_weekly_report_new(account, response, previous_week_stats)
        else:
            # Используем стандартный формат для недельного отчета
            message_text = f"📈 *Статистика за период: {response['period']} - {account.name}*\n\n"
        
            # Звонки
            message_text += f"📞 *Звонки:*\n"
            message_text += f"   • Всего: {response['calls']['total']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['calls']['total'], previous_week_stats.total_calls)
                message_text += f" {format_percentage_change(percentage)}\n"
            else:
                message_text += "\n"
                
            message_text += f"   • Отвечено: {response['calls']['answered']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['calls']['answered'], previous_week_stats.answered_calls)
                message_text += f" {format_percentage_change(percentage)}\n"
            else:
                message_text += "\n"
                
            message_text += f"   • Пропущено: {response['calls']['missed']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['calls']['missed'], previous_week_stats.missed_calls)
                message_text += f" {format_percentage_change(percentage)}\n\n"
            else:
                message_text += "\n\n"
            
            # Сообщения
            message_text += f"💬 *Сообщения:*\n"
            message_text += f"   • Новых за неделю: {response['chats']['total']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['chats']['total'], previous_week_stats.total_chats)
                message_text += f" {format_percentage_change(percentage)}\n"
            else:
                message_text += "\n"
                
            message_text += f"📱 *Показов телефона:* {response['phones_received']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['phones_received'], previous_week_stats.phones_received)
                message_text += f" {format_percentage_change(percentage)}\n\n"
            else:
                message_text += "\n\n"
            
            # Рейтинг и отзывы
            message_text += f"⭐ *Рейтинг:* {response['rating']}\n"
            message_text += f"👍 *Отзывы:*\n"
            message_text += f"   • Всего: {response['reviews']['total']}\n"
            message_text += f"   • За неделю: {response['reviews']['weekly']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['reviews']['weekly'], previous_week_stats.daily_reviews)
                message_text += f" {format_percentage_change(percentage)}\n\n"
            else:
                message_text += "\n\n"
            
            # Объявления
            message_text += f"📝 *Объявления:*\n"
            message_text += f"   • Всего: {response['items']['total']}\n"
            message_text += f"   • С XL продвижением: {response['items']['with_xl_promotion']}\n\n"
            
            # Статистика просмотров
            message_text += f"👁 *Просмотры:* {response['statistics']['views']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['statistics']['views'], previous_week_stats.views)
                message_text += f" {format_percentage_change(percentage)}\n"
            else:
                message_text += "\n"
                
            message_text += f"📲 *Контакты:* {response['statistics']['contacts']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['statistics']['contacts'], previous_week_stats.contacts)
                message_text += f" {format_percentage_change(percentage)}\n"
            else:
                message_text += "\n"
                
            message_text += f"❤️ *В избранном:* {response['statistics']['favorites']}"
            if previous_week_stats:
                percentage = calculate_percentage_change(response['statistics']['favorites'], previous_week_stats.favorites)
                message_text += f" {format_percentage_change(percentage)}\n\n"
            else:
                message_text += "\n\n"
            
            # Финансы
            message_text += f"💰 *Финансы:*\n"
            message_text += f"   • Реальный баланс: {response['balance_real']} ₽\n"
            message_text += f"   • Бонусы: {response['balance_bonus']} ₽\n"
            message_text += f"   • Аванс: {response['advance']} ₽\n\n"
            
            message_text += f"💸 *Расходы за неделю:* "
            
            # Добавляем расходы и детализацию
            expenses_message = format_expenses_message(response.get('expenses', {}))
            message_text += expenses_message
            
            if previous_week_stats and previous_week_stats.daily_expense > 0:
                percentage = calculate_percentage_change(account.weekly_expense, previous_week_stats.daily_expense)
                message_text += f"\n*Изменение расходов: {format_percentage_change(percentage)}*"
        
        # Отправляем отчет на указанный ID для недельных отчетов
        bot.send_message(telegram_id, message_text, parse_mode="Markdown")
        
    except AvitoAccount.DoesNotExist:
        bot.send_message(telegram_id, "❌ Ошибка: аккаунт не найден")
    except Exception as e:
        logger.error(f"Ошибка при отправке недельного отчета: {e}")
        bot.send_message(telegram_id, f"❌ Произошла ошибка: {str(e)}")

def send_daily_report(telegram_id, account_id):
    """Отправка дневного отчета по ID в Telegram и ID аккаунта Авито"""
    try:
        account = AvitoAccount.objects.get(id=account_id)
        client_id = account.client_id
        client_secret = account.client_secret
        response = get_daily_statistics(client_id, client_secret)
        
        # Получаем дату текущего отчета в формате datetime.date
        today_date = datetime.datetime.strptime(response['date'], '%Y-%m-%d').date()
        
        # Получаем статистику за предыдущий день
        previous_stats = get_previous_day_stats(account_id, today_date)
        
        # Проверяем текущий формат отчета
        report_format = Settings.get_value("report_format", "new")
        
        # Используем соответствующий формат отчета
        if report_format == "new":
            message_text = format_daily_report_new(account, response, previous_stats)
        else:
            message_text = format_daily_report_standard(account, response, previous_stats)
        
        bot.send_message(telegram_id, message_text, parse_mode="Markdown")
        
    except AvitoAccount.DoesNotExist:
        bot.send_message(telegram_id, "❌ Ошибка: аккаунт не найден")
    except Exception as e:
        logger.error(f"Ошибка при отправке дневного отчета: {e}")
        bot.send_message(telegram_id, f"❌ Произошла ошибка: {str(e)}")

def add_avito_account(message):
    """Обработчик для добавления нового аккаунта Авито"""
    from bot.handlers.registration import add_avito_account as register_new_account
    register_new_account(message)

def get_daily_reports_for_chat(chat_id):
    """Получение дневных отчетов для всех аккаунтов, связанных с чатом по daily_report_tg_id"""
    # Получаем все аккаунты с указанным ID чата для дневных отчетов
    accounts = AvitoAccount.objects.filter(
        models.Q(daily_report_tg_id=str(chat_id)) | models.Q(daily_report_tg_id=chat_id),
        client_id__isnull=False, 
        client_secret__isnull=False
    ).exclude(client_id="none").distinct()
    
    logger.info(f"ОТЛАДКА: Найдено аккаунтов Авито для дневных отчетов по chat_id={chat_id}: {accounts.count()}")
    
    if not accounts.exists():
        # В целях безопасности показываем сообщение только если чат привязан
        bot.send_message(chat_id, f"К данному чату (ID: {chat_id}) не прилинкован ни один авито аккаунт. Укажите этот ID в поле daily_report_tg_id авито аккаунта через админ панель.")
        return
    
    # Для каждого аккаунта получаем отчет
    for account in accounts:
        daily_report_for_account(chat_id, account.id)

def get_weekly_reports_for_chat(chat_id):
    """Получение недельных отчетов для всех аккаунтов, связанных с чатом по weekly_report_tg_id"""
    # Получаем все аккаунты с указанным ID чата для недельных отчетов
    accounts = AvitoAccount.objects.filter(
        models.Q(weekly_report_tg_id=str(chat_id)) | models.Q(weekly_report_tg_id=chat_id),
        client_id__isnull=False, 
        client_secret__isnull=False
    ).exclude(client_id="none").distinct()
    
    logger.info(f"ОТЛАДКА: Найдено аккаунтов Авито для недельных отчетов по chat_id={chat_id}: {accounts.count()}")
    
    if not accounts.exists():
        # В целях безопасности показываем сообщение только если чат привязан
        bot.send_message(chat_id, f"К данному чату (ID: {chat_id}) не прилинкован ни один авито аккаунт. Укажите этот ID в поле weekly_report_tg_id авито аккаунта через админ панель.")
        return
    
    # Для каждого аккаунта получаем отчет
    for account in accounts:
        weekly_report_for_account(chat_id, account.id)

def get_historical_stats(account_id, days=7):
    """
    Получение исторической статистики из БД для аккаунта за указанное количество дней
    
    Args:
        account_id: ID аккаунта Авито
        days: Количество дней для выборки (по умолчанию 7)
        
    Returns:
        dict: Словарь со статистикой по дням
    """
    try:
        # Проверяем существование аккаунта
        account = AvitoAccount.objects.get(id=account_id)
        
        # Получаем текущую дату
        today = timezone.now().date()
        start_date = today - datetime.timedelta(days=days)
        
        # Получаем все записи статистики для данного аккаунта за указанный период
        stats = AvitoAccountDailyStats.objects.filter(
            avito_account=account,
            date__gte=start_date,
            date__lt=today
        ).order_by('date')
        
        # Если нет данных статистики, возвращаем пустой словарь
        if not stats.exists():
            # Попробуем получить хотя бы последние доступные данные
            last_stats = AvitoAccountDailyStats.objects.filter(
                avito_account=account
            ).order_by('-date').first()
            
            if last_stats:
                logger.info(f"Нет данных за последние {days} дней, но найдены данные за {last_stats.date} для аккаунта {account.name}")
            else:
                logger.info(f"Нет исторической статистики для аккаунта {account.name}")
            
            # В любом случае возвращаем пустой словарь
            return {}
        
        # Сначала подготовим полный список всех дат в запрошенном периоде
        all_dates = []
        current_date = start_date
        while current_date < today:
            all_dates.append(current_date)
            current_date = current_date + datetime.timedelta(days=1)
            
        # Создадим словарь {дата: данные} для быстрого доступа
        stats_by_date = {stat.date: stat for stat in stats}
        
        # Формируем результат
        result = {
            "account_name": account.name,
            "period": f"{start_date} - {today - datetime.timedelta(days=1)}",
            "days_count": days,
            "days": [],
            "days_with_data": stats.count(),
            "days_missing": days - stats.count()
        }
        
        # Добавляем статистику по всем дням в периоде
        # (включая дни без данных, чтобы сохранить хронологию)
        for date in all_dates:
            if date in stats_by_date:
                stat = stats_by_date[date]
                day_stats = {
                    "date": date.strftime("%Y-%m-%d"),
                    "has_data": True,
                    "calls": {
                        "total": stat.total_calls,
                        "answered": stat.answered_calls,
                        "missed": stat.missed_calls
                    },
                    "chats": {
                        "total": stat.total_chats,
                        "new": stat.new_chats
                    },
                    "phones_received": stat.phones_received,
                    "rating": stat.rating,
                    "reviews": {
                        "total": stat.total_reviews,
                        "daily": stat.daily_reviews
                    },
                    "items": {
                        "total": stat.total_items,
                        "with_xl_promotion": stat.xl_promotion_count
                    },
                    "statistics": {
                        "views": stat.views,
                        "contacts": stat.contacts,
                        "favorites": stat.favorites
                    },
                    "finance": {
                        "balance_real": stat.balance_real,
                        "balance_bonus": stat.balance_bonus,
                        "advance": stat.advance,
                        "expense": stat.daily_expense
                    },
                    "expenses_details": stat.get_expenses_details()
                }
            else:
                # Если данных за этот день нет, добавляем заглушку
                day_stats = {
                    "date": date.strftime("%Y-%m-%d"),
                    "has_data": False
                }
            
            result["days"].append(day_stats)
        
        # Добавляем суммарную статистику за весь период
        # Учитываем только дни, для которых есть данные
        days_with_data = [day for day in result["days"] if day.get("has_data", False)]
        
        if days_with_data:
            total_stats = {
                "calls": {
                    "total": sum(day["calls"]["total"] for day in days_with_data),
                    "answered": sum(day["calls"]["answered"] for day in days_with_data),
                    "missed": sum(day["calls"]["missed"] for day in days_with_data)
                },
                "chats": {
                    "total": sum(day["chats"]["total"] for day in days_with_data)
                },
                "phones_received": sum(day["phones_received"] for day in days_with_data),
                "statistics": {
                    "views": sum(day["statistics"]["views"] for day in days_with_data),
                    "contacts": sum(day["statistics"]["contacts"] for day in days_with_data),
                    "favorites": sum(day["statistics"]["favorites"] for day in days_with_data)
                },
                "daily_reviews": sum(day["reviews"]["daily"] for day in days_with_data),
                "expenses": sum(day["finance"]["expense"] for day in days_with_data)
            }
            
            # Добавляем среднедневные значения
            if result["days_with_data"] > 0:
                total_stats["daily_avg"] = {
                    "calls": round(total_stats["calls"]["total"] / result["days_with_data"], 1),
                    "views": round(total_stats["statistics"]["views"] / result["days_with_data"], 1),
                    "contacts": round(total_stats["statistics"]["contacts"] / result["days_with_data"], 1),
                    "expenses": round(total_stats["expenses"] / result["days_with_data"], 2)
                }
            
            result["total"] = total_stats
        
        logger.info(f"Получена историческая статистика для аккаунта {account.name} за {days} дней")
        return result
        
    except AvitoAccount.DoesNotExist:
        logger.error(f"Аккаунт с ID {account_id} не найден")
        return {}
    except Exception as e:
        logger.error(f"Ошибка при получении исторической статистики: {e}")
        return {}

def format_historical_stats_message(stats_data):
    """
    Форматирует историческую статистику для сообщения
    
    Args:
        stats_data: Словарь со статистикой
        
    Returns:
        str: Отформатированное сообщение
    """
    if not stats_data:
        return "📊 *Нет исторической статистики за указанный период*"
    
    message = f"📈 *Статистика за период: {stats_data['period']} - {stats_data['account_name']}*\n\n"
    
    # Добавляем информацию о покрытии данными
    days_count = stats_data.get('days_count', 0)
    days_with_data = stats_data.get('days_with_data', 0)
    days_missing = stats_data.get('days_missing', 0)
    
    if days_missing > 0:
        coverage_percent = (days_with_data / days_count) * 100 if days_count > 0 else 0
        message += f"ℹ️ *Доступность данных:* {days_with_data} из {days_count} дней ({coverage_percent:.1f}%)\n\n"
    
    # Добавляем суммарную статистику
    total = stats_data.get('total', {})
    
    message += f"📞 *Звонки (всего):*\n"
    message += f"   • Всего: {total.get('calls', {}).get('total', 0)}\n"
    message += f"   • Отвечено: {total.get('calls', {}).get('answered', 0)}\n"
    message += f"   • Пропущено: {total.get('calls', {}).get('missed', 0)}\n\n"
    
    message += f"💬 *Чаты (всего):* {total.get('chats', {}).get('total', 0)}\n"
    message += f"📱 *Показов телефона (всего):* {total.get('phones_received', 0)}\n\n"
    
    message += f"👍 *Новых отзывов:* {total.get('daily_reviews', 0)}\n\n"
    
    message += f"👁 *Просмотры (всего):* {total.get('statistics', {}).get('views', 0)}\n"
    message += f"📲 *Контакты (всего):* {total.get('statistics', {}).get('contacts', 0)}\n"
    message += f"❤️ *В избранном (всего):* {total.get('statistics', {}).get('favorites', 0)}\n\n"
    
    message += f"💸 *Расходы за период:* {total.get('expenses', 0):.2f} ₽\n\n"
    
    # Добавляем среднедневные показатели
    daily_avg = total.get('daily_avg', {})
    if daily_avg:
        message += f"📊 *Среднедневные показатели:*\n"
        message += f"   • Звонки: {daily_avg.get('calls', 0)} в день\n"
        message += f"   • Просмотры: {daily_avg.get('views', 0)} в день\n"
        message += f"   • Контакты: {daily_avg.get('contacts', 0)} в день\n"
        message += f"   • Расходы: {daily_avg.get('expenses', 0):.2f} ₽ в день\n\n"
    
    # Добавляем статистику по дням в обратном порядке (от новых к старым)
    message += f"📅 *Статистика по дням:*\n"
    
    # Фильтруем только дни с данными
    days_with_data = [day for day in stats_data.get('days', []) if day.get('has_data', False)]
    
    # Ограничиваем количество дней в детализации
    max_days_in_details = 10
    days_to_show = days_with_data[-max_days_in_details:] if len(days_with_data) > max_days_in_details else days_with_data
    days_to_show = list(reversed(days_to_show))  # Сортируем от новых к старым
    
    # Если данных слишком много, добавим примечание
    if len(days_with_data) > max_days_in_details:
        message += f"_(показаны последние {max_days_in_details} дней из {len(days_with_data)})_\n"
    
    for day in days_to_show:
        date = day.get('date', '')
        calls = day.get('calls', {}).get('total', 0)
        views = day.get('statistics', {}).get('views', 0)
        contacts = day.get('statistics', {}).get('contacts', 0)
        expense = day.get('finance', {}).get('expense', 0)
        
        message += f"\n*{date}*:\n"
        message += f"   • Звонки: {calls}, Просмотры: {views}, Контакты: {contacts}\n"
        message += f"   • Расходы: {expense:.2f} ₽\n"
    
    return message

def format_daily_report_new(account, response, previous_stats):
    """
    Форматирует дневной отчет в новом формате
    
    Args:
        account: Экземпляр модели AvitoAccount
        response: Словарь с данными статистики
        previous_stats: Статистика за предыдущий день (модель AvitoAccountDailyStats) или None
        
    Returns:
        str: Отформатированное сообщение
    """
    # Форматируем дату
    date_obj = datetime.datetime.strptime(response['date'], '%Y-%m-%d').date()
    formatted_date = date_obj.strftime('%d.%m.%Y')
    
    # Начало сообщения с именем аккаунта
    message_text = f"> {account.name}:\nОтчет за {formatted_date}\n\n"
    
    # Секция "Показатели"
    message_text += f"Показатели\n"
    
    # Объявления
    total_items = response['items']['total']
    percentage_items = 0
    if previous_stats:
        percentage_items = calculate_percentage_change(total_items, previous_stats.total_items)
    message_text += f"✔️Объявления: {total_items} шт ({format_simple_percentage(percentage_items)})\n"
    
    # Просмотры
    views = response['statistics']['views']
    percentage_views = 0
    if previous_stats:
        percentage_views = calculate_percentage_change(views, previous_stats.views)
    message_text += f"✔️Просмотры: {views} ({format_simple_percentage(percentage_views)})\n"
    
    # Контакты
    contacts = response['statistics']['contacts']
    percentage_contacts = 0
    if previous_stats:
        percentage_contacts = calculate_percentage_change(contacts, previous_stats.contacts)
    message_text += f"✔️Контакты: {contacts} ({format_simple_percentage(percentage_contacts)})\n"
    
    # Конверсия в контакты
    conversion = 0
    percentage_conversion = 0
    if views > 0:
        conversion = (contacts / views) * 100
        if previous_stats and previous_stats.views > 0:
            prev_conversion = (previous_stats.contacts / previous_stats.views) * 100
            percentage_conversion = calculate_percentage_change(conversion, prev_conversion)
    message_text += f"✔️Конверсия в контакты: {conversion:.1f}% ({format_simple_percentage(percentage_conversion)})\n"
    
    # Стоимость контакта
    contact_cost = 0
    percentage_contact_cost = 0
    
    # Безопасное получение общих расходов
    expenses_total = 0
    try:
        # Если expenses - словарь с ключом total, берем значение
        if isinstance(response.get('expenses', {}), dict) and 'total' in response.get('expenses', {}):
            expenses_val = response.get('expenses', {}).get('total', 0)
            if isinstance(expenses_val, (int, float)):
                expenses_total = expenses_val
        # Иначе берем расход из аккаунта
        else:
            expenses_total = getattr(account, 'daily_expense', 0)
    except Exception as e:
        logger.error(f"Ошибка при обработке расходов: {e}")
        # В случае ошибки используем значение из аккаунта
        expenses_total = getattr(account, 'daily_expense', 0)
        
    if contacts > 0 and expenses_total > 0:
        contact_cost = expenses_total / contacts
        if previous_stats and previous_stats.contacts > 0 and previous_stats.daily_expense > 0:
            prev_contact_cost = previous_stats.daily_expense / previous_stats.contacts
            percentage_contact_cost = calculate_percentage_change(contact_cost, prev_contact_cost)
    message_text += f"✔️Стоимость контакта: {contact_cost:.0f} ₽ ({format_simple_percentage(percentage_contact_cost)})\n"
    
    # Звонки
    calls = response['calls']['total']
    percentage_calls = 0
    if previous_stats:
        percentage_calls = calculate_percentage_change(calls, previous_stats.total_calls)
    # Используем ❗️ если процент отрицательный
    call_indicator = "❗️" if percentage_calls < 0 else "✔️"
    message_text += f"{call_indicator}Всего звонков: {calls} ({format_simple_percentage(percentage_calls)})\n\n"
    
    # Секция "Расходы"
    message_text += f"Расходы\n"
    
    # Общие расходы
    percentage_expenses = 0
    if previous_stats and previous_stats.daily_expense > 0:
        percentage_expenses = calculate_percentage_change(expenses_total, previous_stats.daily_expense)
    message_text += f"Общие: {response['expenses']['total'] / 100:,} ₽ ({format_simple_percentage(percentage_expenses)})\n".replace(',', ' ')
    
    # Расходы на продвижение
    # Изменил вместо 0
    promo_expense = response['expenses']['details']['promo']['amount'] / 100
    percentage_promo = 0
    message_text += f"На продвижение: {promo_expense:,} ₽ ({format_simple_percentage(percentage_promo)})\n".replace(',', ' ')
    
    # Расходы на XL и выделение
    xl_expense = response['expenses']['details']['presense']['amount'] / 100
    percentage_xl = 0
    message_text += f"На XL и выделение: {xl_expense:,} ₽ ({format_simple_percentage(percentage_xl)})\n".replace(',', ' ')
    
    # Рассылка скидок
    discount_expense = response['expenses']['details']['sales']['amount']
    percentage_discount = 0
    message_text += f"Рассылка скидок: {discount_expense:,} ₽ ({format_simple_percentage(percentage_discount)})\n\n".replace(',', ' ')
    
    # Работа менеджеров
    message_text += f"Работа менеджеров\n"
    
    # Непринятые звонки
    missed_calls = response['calls']['missed']
    message_text += f"Непринятые звонки: {missed_calls}\n"
    
    # Сообщения без ответа (оценка)
    unanswered_messages = 0
    if isinstance(response.get('chats', {}), dict):
        unanswered_messages = response.get('chats', {}).get('unanswered', 0)
    message_text += f"Сообщения без ответа: {unanswered_messages}\n"
    
    # Уровень сервиса
    service_level = 0
    if calls > 0:
        answered_calls = calls - missed_calls
        service_level = (answered_calls / calls) * 100
    message_text += f"Уровень сервиса: {service_level:.0f}%\n"
    
    # Новые отзывы
    new_reviews = response['reviews']['today']
    message_text += f"Новые отзывы: {new_reviews}\n\n"
    
    # Балансы
    message_text += f"—————————\n"
    message_text += f"CPA баланс: {response['balance_real']:,} ₽\n".replace(',', ' ')
    
    # Кошелек (сумма реального баланса и бонусов)
    wallet = response['balance_real'] + response['balance_bonus']
    message_text += f"Кошелек: {wallet:,} ₽".replace(',', ' ')
    
    return message_text

def format_simple_percentage(percentage):
    """
    Форматирует процентное изменение в простой форме +X% или -X%
    
    Args:
        percentage: Процентное изменение
        
    Returns:
        str: Отформатированная строка с процентом
    """
    if percentage > 0:
        return f"+{percentage:.1f}%"
    elif percentage < 0:
        return f"{percentage:.1f}%"
    else:
        return "0.0%"

def toggle_report_format(message):
    """Обработчик команды для переключения формата отчета"""
    try:
        chat_id = message.chat.id
        
        # Проверка прав администратора (опционально)
        try:
            user = User.objects.get(telegram_id=str(message.from_user.id))
        except User.DoesNotExist:
            bot.send_message(chat_id, "❌ Только зарегистрированные пользователи могут менять формат отчета")
            return
            
        # Создаем сообщение с кнопками выбора
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(
            telebot.types.InlineKeyboardButton("Новый формат", callback_data="report_format_new"),
            telebot.types.InlineKeyboardButton("Стандартный формат", callback_data="report_format_standard")
        )
        
        bot.send_message(
            chat_id,
            "Выберите предпочитаемый формат отчета:",
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Ошибка при выборе формата отчета: {e}")
        bot.send_message(chat_id, f"❌ Произошла ошибка: {str(e)}")

# Обработчик выбора формата отчета
def handle_report_format_selection(call):
    """Обработчик выбора формата отчета из inline-кнопок"""
    chat_id = call.message.chat.id
    
    try:
        # Получаем всех пользователей, связанных с этим chat_id
        users = User.objects.filter(telegram_id=str(call.from_user.id))
        
        if not users.exists():
            bot.answer_callback_query(call.id, "Доступно только для зарегистрированных пользователей")
            return
            
        # Устанавливаем настройку формата отчета в базе данных
        if call.data == "report_format_new":
            Settings.set_value(
                key="report_format", 
                value="new",
                description="Формат вывода отчетов (new/standard)"
            )
            bot.answer_callback_query(call.id, "Установлен новый формат отчета")
            bot.edit_message_text(
                "✅ Установлен новый формат отчета",
                chat_id,
                call.message.message_id,
                reply_markup=None
            )
        else:
            Settings.set_value(
                key="report_format", 
                value="standard",
                description="Формат вывода отчетов (new/standard)"
            )
            bot.answer_callback_query(call.id, "Установлен стандартный формат отчета")
            bot.edit_message_text(
                "✅ Установлен стандартный формат отчета",
                chat_id,
                call.message.message_id,
                reply_markup=None
            )
            
    except Exception as e:
        logger.error(f"Ошибка при сохранении формата отчета: {e}")
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

def format_daily_report_standard(account, response, previous_stats):
    """
    Форматирует дневной отчет в стандартном формате
    
    Args:
        account: Экземпляр модели AvitoAccount
        response: Словарь с данными статистики
        previous_stats: Статистика за предыдущий день (модель AvitoAccountDailyStats) или None
        
    Returns:
        str: Отформатированное сообщение
    """
    # Формируем читаемое сообщение для пользователя
    message_text = f"📊 *Статистика за {response['date']} - {account.name}*\n\n"
    
    # Звонки
    message_text += f"📞 *Звонки:*\n"
    message_text += f"   • Всего: {response['calls']['total']}"
    if previous_stats:
        percentage = calculate_percentage_change(response['calls']['total'], previous_stats.total_calls)
        message_text += f" {format_percentage_change(percentage)}\n"
    else:
        message_text += "\n"
        
    message_text += f"   • Отвечено: {response['calls']['answered']}"
    if previous_stats:
        percentage = calculate_percentage_change(response['calls']['answered'], previous_stats.answered_calls)
        message_text += f" {format_percentage_change(percentage)}\n"
    else:
        message_text += "\n"
        
    message_text += f"   • Пропущено: {response['calls']['missed']}"
    if previous_stats:
        percentage = calculate_percentage_change(response['calls']['missed'], previous_stats.missed_calls)
        message_text += f" {format_percentage_change(percentage)}\n\n"
    else:
        message_text += "\n\n"
    
    # Сообщения
    message_text += f"💬 *Сообщения:*\n"
    message_text += f"   • Новых за день: {response['chats']['total']}"
    if previous_stats:
        percentage = calculate_percentage_change(response['chats']['total'], previous_stats.total_chats)
        message_text += f" {format_percentage_change(percentage)}\n"
    else:
        message_text += "\n"
        
    message_text += f"📱 *Показов телефона:* {response['phones_received']}"
    if previous_stats:
        percentage = calculate_percentage_change(response['phones_received'], previous_stats.phones_received)
        message_text += f" {format_percentage_change(percentage)}\n\n"
    else:
        message_text += "\n\n"
    
    # Рейтинг и отзывы
    message_text += f"⭐ *Рейтинг:* {response['rating']}\n"
    message_text += f"👍 *Отзывы:*\n"
    message_text += f"   • Всего: {response['reviews']['total']}\n"
    message_text += f"   • За день: {response['reviews']['today']}"
    if previous_stats:
        percentage = calculate_percentage_change(response['reviews']['today'], previous_stats.daily_reviews)
        message_text += f" {format_percentage_change(percentage)}\n\n"
    else:
        message_text += "\n\n"
    
    # Объявления
    message_text += f"📝 *Объявления:*\n"
    message_text += f"   • Всего: {response['items']['total']}\n"
    message_text += f"   • С XL продвижением: {response['items']['with_xl_promotion']}\n\n"
    
    # Статистика просмотров
    message_text += f"👁 *Просмотры:* {response['statistics']['views']}"
    if previous_stats:
        percentage = calculate_percentage_change(response['statistics']['views'], previous_stats.views)
        message_text += f" {format_percentage_change(percentage)}\n"
    else:
        message_text += "\n"
        
    message_text += f"📲 *Контакты:* {response['statistics']['contacts']}"
    if previous_stats:
        percentage = calculate_percentage_change(response['statistics']['contacts'], previous_stats.contacts)
        message_text += f" {format_percentage_change(percentage)}\n"
    else:
        message_text += "\n"
        
    message_text += f"❤️ *В избранном:* {response['statistics']['favorites']}"
    if previous_stats:
        percentage = calculate_percentage_change(response['statistics']['favorites'], previous_stats.favorites)
        message_text += f" {format_percentage_change(percentage)}\n\n"
    else:
        message_text += "\n\n"
    
    # Финансы
    message_text += f"💰 *Финансы:*\n"
    message_text += f"   • Реальный баланс: {response['balance_real']} ₽\n"
    message_text += f"   • Бонусы: {response['balance_bonus']} ₽\n"
    message_text += f"   • Аванс: {response['advance']} ₽\n\n"
    
    message_text += f"💸 *Расходы за день:* "
    expenses_message = format_expenses_message(response.get('expenses', {}))
    message_text += expenses_message
    
    if previous_stats and previous_stats.daily_expense > 0:
        percentage = calculate_percentage_change(account.daily_expense, previous_stats.daily_expense)
        message_text += f"\n*Изменение расходов: {format_percentage_change(percentage)}*"
    
    return message_text

def format_weekly_report_new(account, response, previous_stats):
    """
    Форматирует недельный отчет в новом формате
    
    Args:
        account: Экземпляр модели AvitoAccount
        response: Словарь с данными статистики
        previous_stats: Статистика за предыдущую неделю (объект с аналогичными полями) или None
        
    Returns:
        str: Отформатированное сообщение
    """
    # Начало сообщения с именем аккаунта и периодом
    message_text = f"> {account.name}:\nОтчет за период: {response['period']}\n\n"
    
    # Секция "Показатели"
    message_text += f"Показатели\n"
    
    # Объявления
    total_items = response['items']['total']
    percentage_items = 0
    if previous_stats:
        percentage_items = calculate_percentage_change(total_items, previous_stats.total_items)
    message_text += f"✔️Объявления: {total_items} шт ({format_simple_percentage(percentage_items)})\n"
    
    # Просмотры
    views = response['statistics']['views']
    percentage_views = 0
    if previous_stats:
        percentage_views = calculate_percentage_change(views, previous_stats.views)
    message_text += f"✔️Просмотры: {views} ({format_simple_percentage(percentage_views)})\n"
    
    # Контакты
    contacts = response['statistics']['contacts']
    percentage_contacts = 0
    if previous_stats:
        percentage_contacts = calculate_percentage_change(contacts, previous_stats.contacts)
    message_text += f"✔️Контакты: {contacts} ({format_simple_percentage(percentage_contacts)})\n"
    
    # Конверсия в контакты
    conversion = 0
    percentage_conversion = 0
    if views > 0:
        conversion = (contacts / views) * 100
        if previous_stats and previous_stats.views > 0:
            prev_conversion = (previous_stats.contacts / previous_stats.views) * 100
            percentage_conversion = calculate_percentage_change(conversion, prev_conversion)
    message_text += f"✔️Конверсия в контакты: {conversion:.1f}% ({format_simple_percentage(percentage_conversion)})\n"
    
    # Стоимость контакта
    contact_cost = 0
    percentage_contact_cost = 0
    
    # Безопасное получение общих расходов
    expenses_total = 0
    try:
        # Если expenses - словарь с ключом total, берем значение
        if isinstance(response.get('expenses', {}), dict) and 'total' in response.get('expenses', {}):
            expenses_val = response.get('expenses', {}).get('total', 0)
            if isinstance(expenses_val, (int, float)):
                expenses_total = expenses_val
        # Иначе берем расход из аккаунта
        else:
            expenses_total = getattr(account, 'weekly_expense', 0)
    except Exception as e:
        logger.error(f"Ошибка при обработке недельных расходов: {e}")
        # В случае ошибки используем значение из аккаунта
        expenses_total = getattr(account, 'weekly_expense', 0)
        
    if contacts > 0 and expenses_total > 0:
        contact_cost = expenses_total / contacts
        if previous_stats and previous_stats.contacts > 0 and previous_stats.daily_expense > 0:
            prev_contact_cost = previous_stats.daily_expense / previous_stats.contacts
            percentage_contact_cost = calculate_percentage_change(contact_cost, prev_contact_cost)
    message_text += f"✔️Стоимость контакта: {contact_cost:.0f} ₽ ({format_simple_percentage(percentage_contact_cost)})\n"
    
    # Звонки
    calls = response['calls']['total']
    percentage_calls = 0
    if previous_stats:
        percentage_calls = calculate_percentage_change(calls, previous_stats.total_calls)
    # Используем ❗️ если процент отрицательный
    call_indicator = "❗️" if percentage_calls < 0 else "✔️"
    message_text += f"{call_indicator}Всего звонков: {calls} ({format_simple_percentage(percentage_calls)})\n\n"
    
    # Секция "Расходы"
    message_text += f"Расходы\n"
    
    # Общие расходы
    percentage_expenses = 0
    if previous_stats and previous_stats.daily_expense > 0:
        percentage_expenses = calculate_percentage_change(expenses_total, previous_stats.daily_expense)
    message_text += f"Общие: {expenses_total / 100:,} ₽ ({format_simple_percentage(percentage_expenses)})\n".replace(',', ' ')
    
    # Расходы на продвижение
    # Изменил вместо 0
    promo_expense = response['expenses']['details']['promo']['amount'] / 100
    percentage_promo = 0
    message_text += f"На продвижение: {promo_expense:,} ₽ ({format_simple_percentage(percentage_promo)})\n".replace(',', ' ')
    
    # Расходы на XL и выделение
    xl_expense = response['expenses']['details']['presense']['amount'] / 100
    percentage_xl = 0
    message_text += f"На XL и выделение: {xl_expense:,} ₽ ({format_simple_percentage(percentage_xl)})\n".replace(',', ' ')
    
    # Рассылка скидок
    discount_expense = response['expenses']['details']['sales']['amount']
    percentage_discount = 0
    message_text += f"Рассылка скидок: {discount_expense:,} ₽ ({format_simple_percentage(percentage_discount)})\n\n".replace(',', ' ')
    
    # Работа менеджеров
    message_text += f"Работа менеджеров\n"
    
    # Непринятые звонки
    missed_calls = response['calls']['missed']
    message_text += f"Непринятые звонки: {missed_calls}\n"
    
    # Сообщения без ответа (оценка)
    unanswered_messages = 0
    if isinstance(response.get('chats', {}), dict):
        unanswered_messages = response.get('chats', {}).get('unanswered', 0)
    message_text += f"Сообщения без ответа: {unanswered_messages}\n"
    
    # Уровень сервиса
    service_level = 0
    if calls > 0:
        answered_calls = calls - missed_calls
        service_level = (answered_calls / calls) * 100
    message_text += f"Уровень сервиса: {service_level:.0f}%\n"
    
    # Новые отзывы за неделю
    new_reviews = response['reviews']['weekly']
    message_text += f"Новые отзывы: {new_reviews}\n\n"
    
    # Балансы
    message_text += f"—————————\n"
    message_text += f"CPA баланс: {response['balance_real']:,} ₽\n".replace(',', ' ')
    
    # Кошелек (сумма реального баланса и бонусов)
    wallet = response['balance_real'] + response['balance_bonus']
    message_text += f"Кошелек: {wallet:,} ₽".replace(',', ' ')
    
    return message_text
