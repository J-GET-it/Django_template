from traceback import format_exc

from asgiref.sync import sync_to_async
from bot.handlers import *
from bot.handlers.common import get_historical_stats, format_historical_stats_message
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from telebot.apihelper import ApiTelegramException
from telebot.types import Update

from bot import bot, logger
import telebot


@require_GET
def set_webhook(request: HttpRequest) -> JsonResponse:
    """Setting webhook."""
    bot.set_webhook(url=f"{settings.HOOK}/bot/{settings.BOT_TOKEN}")
    bot.send_message(settings.OWNER_ID, "webhook set")
    return JsonResponse({"message": "OK"}, status=200)


@require_GET
def status(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"message": "OK"}, status=200)


@csrf_exempt
@require_POST
@sync_to_async
def index(request: HttpRequest) -> JsonResponse:
    if request.META.get("CONTENT_TYPE") != "application/json":
        return JsonResponse({"message": "Bad Request"}, status=403)

    json_string = request.body.decode("utf-8")
    update = Update.de_json(json_string)
    try:
        bot.process_new_updates([update])
    except ApiTelegramException as e:
        logger.error(f"Telegram exception. {e} {format_exc()}")
    except ConnectionError as e:
        logger.error(f"Connection error. {e} {format_exc()}")
    except Exception as e:
        bot.send_message(settings.OWNER_ID, f'Error from index: {e}')
        logger.error(f"Unhandled exception. {e} {format_exc()}")
    return JsonResponse({"message": "OK"}, status=200)


"""Common"""
admin = bot.message_handler(commands=["admin"])(get_users)

# Создаем обертку для команды start, чтобы использовать chat_id
@bot.message_handler(commands=["start"])
def start_command(message):
    """Обработчик команды /start"""
    from bot.handlers.common import start
    chat_id = message.chat.id
    logger.info(f"ОТЛАДКА: Команда /start в чате {chat_id} от пользователя {message.from_user.id}")
    start(message)

get_user_info = bot.callback_query_handler(lambda c: c.data.startswith("admin_"))(get_user_info)

# Добавляем функцию-посредник для отладки daily_report
def daily_report_wrapper(call):
    logger.info(f"ОТЛАДКА: Обработка daily_report callback: {call.data}")
    logger.info(f"ОТЛАДКА: from_user.id = {call.from_user.id}, chat_id = {call.message.chat.id}")
    try:
        daily_report(call)
    except Exception as e:
        logger.error(f"Ошибка в daily_report_wrapper: {e}")
        logger.exception("Полный стек-трейс ошибки:")
        bot.send_message(call.message.chat.id, f"❌ Произошла ошибка: {str(e)}")

# Добавляем функцию-посредник для отладки weekly_report
def weekly_report_wrapper(call):
    logger.info(f"ОТЛАДКА: Обработка weekly_report callback: {call.data}")
    logger.info(f"ОТЛАДКА: from_user.id = {call.from_user.id}, chat_id = {call.message.chat.id}")
    try:
        weekly_report(call)
    except Exception as e:
        logger.error(f"Ошибка в weekly_report_wrapper: {e}")
        logger.exception("Полный стек-трейс ошибки:")
        bot.send_message(call.message.chat.id, f"❌ Произошла ошибка: {str(e)}")

# Функция-посредник для обработки запросов на историческую статистику
def historical_stats_wrapper(call):
    logger.info(f"ОТЛАДКА: Обработка historical_stats callback: {call.data}")
    logger.info(f"ОТЛАДКА: from_user.id = {call.from_user.id}, chat_id = {call.message.chat.id}")
    try:
        # Разбираем callback_data, чтобы получить период и ID аккаунта
        parts = call.data.split("_")
        if len(parts) >= 4 and parts[0] == "stats":
            period = parts[1]
            account_id = int(parts[3])
            
            # Определяем количество дней в зависимости от запрошенного периода
            if period == "7d":
                days = 7
                period_name = "7 дней"
            elif period == "14d":
                days = 14
                period_name = "14 дней"
            elif period == "30d":
                days = 30
                period_name = "30 дней"
            else:
                days = 7
                period_name = "7 дней"
                
            # Отправляем сообщение о загрузке
            loading_message = bot.send_message(
                call.message.chat.id, 
                f"⏳ Получаем статистику за последние {period_name}..."
            )
            
            # Получаем историческую статистику
            stats = get_historical_stats(account_id, days)
            
            # Удаляем сообщение о загрузке
            bot.delete_message(call.message.chat.id, loading_message.message_id)
            
            # Форматируем и отправляем статистику
            message = format_historical_stats_message(stats)
            bot.send_message(call.message.chat.id, message, parse_mode="Markdown")
        else:
            bot.send_message(call.message.chat.id, "❌ Некорректный формат запроса")
    except Exception as e:
        logger.error(f"Ошибка в historical_stats_wrapper: {e}")
        logger.exception("Полный стек-трейс ошибки:")
        bot.send_message(call.message.chat.id, f"❌ Произошла ошибка: {str(e)}")

# Обработчик дневных отчетов из кнопок меню и кнопок выбора аккаунта
daily_report_handler = bot.callback_query_handler(func=lambda c: c.data == "daily_report" or c.data.startswith("daily_report_"))(daily_report_wrapper)

# Обработчик недельных отчетов из кнопок меню и кнопок выбора аккаунта
weekly_report_handler = bot.callback_query_handler(func=lambda c: c.data == "weekly_report" or c.data.startswith("weekly_report_"))(weekly_report_wrapper)

# Обработчик исторической статистики за разные периоды
historical_stats_handler = bot.callback_query_handler(func=lambda c: c.data.startswith("stats_"))(historical_stats_wrapper)

@bot.message_handler(commands=["daily"])
def daily_command(message):
    """Обработчик команды /daily для получения дневного отчета"""
    from bot.handlers.common import get_daily_reports_for_chat
    chat_id = message.chat.id
    logger.info(f"ОТЛАДКА: Команда /daily в чате {chat_id} от пользователя {message.from_user.id}")
    get_daily_reports_for_chat(chat_id)

@bot.message_handler(commands=["weekly"])
def weekly_command(message):
    """Обработчик команды /weekly для получения недельного отчета"""
    from bot.handlers.common import get_weekly_reports_for_chat
    chat_id = message.chat.id
    logger.info(f"ОТЛАДКА: Команда /weekly в чате {chat_id} от пользователя {message.from_user.id}")
    get_weekly_reports_for_chat(chat_id)

@bot.message_handler(commands=["stats"])
def stats_command(message):
    """Обработчик команды /stats для получения исторической статистики"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    logger.info(f"ОТЛАДКА: Команда /stats в чате {chat_id} от пользователя {user_id}")
    
    try:
        from bot.models import AvitoAccount
        
        # Получаем все аккаунты Авито в системе
        accounts = AvitoAccount.objects.filter(
            client_id__isnull=False,
            client_secret__isnull=False
        ).exclude(client_id="none").distinct()
        
        if not accounts.exists():
            bot.send_message(chat_id, "❌ В системе нет зарегистрированных аккаунтов Авито")
            return
            
        if accounts.count() == 1:
            # Если только один аккаунт, сразу показываем варианты периодов статистики
            account_id = accounts.first().id
            account_name = accounts.first().name
            
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton(
                text="За 7 дней", 
                callback_data=f"stats_7d_acc_{account_id}"
            ))
            markup.add(telebot.types.InlineKeyboardButton(
                text="За 14 дней", 
                callback_data=f"stats_14d_acc_{account_id}"
            ))
            markup.add(telebot.types.InlineKeyboardButton(
                text="За 30 дней", 
                callback_data=f"stats_30d_acc_{account_id}"
            ))
            
            bot.send_message(
                chat_id=chat_id,
                text=f"📊 Выберите период для просмотра статистики аккаунта *{account_name}*:",
                reply_markup=markup,
                parse_mode="Markdown"
            )
            return
            
        # Если несколько аккаунтов, предлагаем выбрать аккаунт
        markup = telebot.types.InlineKeyboardMarkup()
        for account in accounts:
            markup.add(telebot.types.InlineKeyboardButton(
                text=account.name,
                callback_data=f"select_stats_acc_{account.id}"
            ))
            
        bot.send_message(
            chat_id=chat_id,
            text="📊 Выберите аккаунт для просмотра статистики:",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /stats: {e}")
        logger.exception("Полный стек-трейс ошибки:")
        bot.send_message(chat_id, f"❌ Произошла ошибка: {str(e)}")

# Обработчик выбора аккаунта для статистики
@bot.callback_query_handler(func=lambda c: c.data.startswith("select_stats_acc_"))
def select_account_for_stats(call):
    chat_id = call.message.chat.id
    logger.info(f"ОТЛАДКА: Выбор аккаунта для статистики: {call.data}")
    
    try:
        # Получаем ID аккаунта из callback_data
        parts = call.data.split("_")
        if len(parts) >= 4:
            account_id = int(parts[3])
            
            from bot.models import AvitoAccount
            account = AvitoAccount.objects.get(id=account_id)
            
            # Предлагаем выбрать период для статистики
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton(
                text="За 7 дней", 
                callback_data=f"stats_7d_acc_{account_id}"
            ))
            markup.add(telebot.types.InlineKeyboardButton(
                text="За 14 дней", 
                callback_data=f"stats_14d_acc_{account_id}"
            ))
            markup.add(telebot.types.InlineKeyboardButton(
                text="За 30 дней", 
                callback_data=f"stats_30d_acc_{account_id}"
            ))
            
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=f"📊 Выберите период для просмотра статистики аккаунта *{account.name}*:",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        else:
            bot.send_message(chat_id, "❌ Некорректный формат запроса")
    except Exception as e:
        logger.error(f"Ошибка при выборе аккаунта для статистики: {e}")
        logger.exception("Полный стек-трейс ошибки:")
        bot.send_message(chat_id, f"❌ Произошла ошибка: {str(e)}")

# Обработчик для кнопки "Статистика за период" из главного меню
@bot.callback_query_handler(func=lambda c: c.data == "stats_menu")
def stats_menu_handler(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    logger.info(f"ОТЛАДКА: Нажата кнопка 'Статистика за период', user_id: {user_id}, chat_id: {chat_id}")
    
    # Вызываем ту же логику, что и для команды /stats
    stats_command(call.message)

@bot.message_handler(commands=["populate"])
def populate_command(message):
    """Обработчик команды /populate для заполнения исторических данных"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Проверяем, что команду вызывает владелец бота
    if str(user_id) != settings.OWNER_ID:
        bot.send_message(chat_id, "❌ У вас нет прав для выполнения этой команды.")
        return
    
    logger.info(f"ОТЛАДКА: Запуск команды /populate от пользователя {user_id}")
    
    try:
        # Запрашиваем количество дней для заполнения
        msg = bot.send_message(
            chat_id,
            "Введите количество дней для заполнения (от 1 до 60):"
        )
        bot.register_next_step_handler(msg, process_populate_days)
    except Exception as e:
        logger.error(f"Ошибка при запуске команды populate: {e}")
        bot.send_message(chat_id, f"❌ Произошла ошибка: {str(e)}")

def process_populate_days(message):
    """Обработка ввода количества дней для заполнения исторических данных"""
    chat_id = message.chat.id
    
    try:
        days = int(message.text.strip())
        if days < 1 or days > 60:
            bot.send_message(chat_id, "❌ Количество дней должно быть от 1 до 60.")
            return
        
        # Отправляем сообщение о начале заполнения
        bot.send_message(
            chat_id,
            f"⏳ Начинаем заполнение исторических данных за {days} дней...\n"
            f"Это может занять продолжительное время. Вы получите уведомление по завершении."
        )
        
        # Запускаем заполнение данных в отдельном потоке
        import threading
        from bot.cron import populate_historical_data
        
        def populate_and_notify():
            try:
                populate_historical_data(days)
                bot.send_message(chat_id, f"✅ Заполнение исторических данных за {days} дней завершено.")
            except Exception as e:
                logger.error(f"Ошибка при заполнении данных: {e}")
                bot.send_message(chat_id, f"❌ Произошла ошибка при заполнении данных: {str(e)}")
        
        # Запускаем в отдельном потоке, чтобы не блокировать бота
        thread = threading.Thread(target=populate_and_notify)
        thread.start()
        
    except ValueError:
        bot.send_message(chat_id, "❌ Пожалуйста, введите корректное число.")
    except Exception as e:
        logger.error(f"Ошибка при обработке ввода дней: {e}")
        bot.send_message(chat_id, f"❌ Произошла ошибка: {str(e)}")

# Регистрация обработчика команды формата отчета
@bot.message_handler(commands=["format"])
def format_command_handler(message):
    """Обработчик команды /format для изменения формата отчета"""
    from bot.handlers.common import toggle_report_format
    toggle_report_format(message)

# Определение функции-обертки для обработчика выбора формата
def handle_report_format_selection_wrapper(call):
    """Обёртка для обработчика выбора формата отчета"""
    from bot.handlers.common import handle_report_format_selection
    handle_report_format_selection(call)

# Регистрация обработчика выбора формата отчета
format_selection_handler = bot.callback_query_handler(func=lambda c: c.data.startswith("report_format_"))(handle_report_format_selection_wrapper)