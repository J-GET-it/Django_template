import requests
import json
import datetime
import logging

logger = logging.getLogger(__name__)

def get_access_token(client_id, client_secret):
    auth_url = 'https://api.avito.ru/token'
    auth_data = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret
    }

    auth_response = requests.post(auth_url, data=auth_data)
    auth_result = json.loads(auth_response.text)

    # Извлечение API ключа из ответа
    access_token = auth_result.get('access_token')
    return access_token

def get_user_calls_stats(access_token, user_id, date_from=None, date_to=None, item_ids=None):
    """Получение статистики звонков через правильный API эндпоинт"""
    try:
        if date_from is None or date_to is None:
            current_time = datetime.datetime.now()
            date_from = (current_time - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
            date_to = current_time.strftime("%Y-%m-%d")
        else:
            # Конвертируем из ISO формата в формат YYYY-MM-DD если нужно
            if 'T' in str(date_from):
                date_from = datetime.datetime.fromisoformat(date_from.replace('Z', '+00:00')).strftime("%Y-%m-%d")
            if 'T' in str(date_to):
                date_to = datetime.datetime.fromisoformat(date_to.replace('Z', '+00:00')).strftime("%Y-%m-%d")

        calls_stats_url = f'https://api.avito.ru/core/v1/accounts/{user_id}/calls/stats/'
        calls_data = {
            'dateFrom': date_from,
            'dateTo': date_to
        }
        
        # Добавляем ID объявлений если они переданы
        if item_ids:
            calls_data['itemIds'] = item_ids[:100]  # Ограничиваем количество

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        logger.info(f"Запрос статистики звонков с {date_from} по {date_to}")
        
        calls_response = requests.post(calls_stats_url, headers=headers, json=calls_data)
        calls_response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if not calls_response.text.strip():
            logger.warning("Получен пустой ответ от API статистики звонков")
            return {"result": {"items": []}}
        
        try:
            calls_result = calls_response.json()
            logger.info(f"Получена статистика звонков для {len(calls_result.get('result', {}).get('items', []))} объявлений")
            return calls_result
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}, содержимое ответа: {calls_response.text[:200]}")
            return {"result": {"items": []}}
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к API статистики звонков: {e}")
        return {"result": {"items": []}}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении статистики звонков: {e}")
        return {"result": {"items": []}}

def get_total_calls(access_token, date_from=None, date_to=None):
    """Подсчет общего количества новых звонков за период"""
    try:
        # Получаем user_id
        user_info = get_user_info(access_token)
        user_id = user_info.get('id')
        
        if not user_id:
            logger.error("Не удалось получить идентификатор пользователя для статистики звонков")
            return 0
        
        # Получаем статистику звонков
        calls_stats = get_user_calls_stats(access_token, user_id, date_from, date_to)
        
        total_new_calls = 0
        
        # Суммируем новые звонки по всем объявлениям и дням
        for item in calls_stats.get('result', {}).get('items', []):
            for day in item.get('days', []):
                total_new_calls += day.get('new', 0)
        
        logger.info(f"Общее количество новых звонков: {total_new_calls}")
        return total_new_calls
    except Exception as e:
        logger.error(f"Ошибка при подсчете общего количества новых звонков: {e}")
        return 0

def get_missed_calls(access_token, date_from=None, date_to=None):
    """Подсчет пропущенных звонков за период"""
    try:
        # Используем старый API для получения пропущенных звонков
        calls_result = get_user_calls(access_token, date_from, date_to)
        missed_calls = sum(1 for call in calls_result.get('calls', []) if call.get('talkDuration', 0) == 0)
        logger.info(f"Количество пропущенных звонков: {missed_calls}")
        return missed_calls
    except Exception as e:
        logger.error(f"Ошибка при подсчете пропущенных звонков: {e}")
        return 0

def get_user_balance_info(access_token, user_id=None):
    """
    Получает подробную информацию о балансе пользователя:
    - balance_real - реальные деньги в кошельке
    - balance_bonus - бонусные средства
    - advance - авансовые платежи (бывший 'balance' из API v3)
    """
    try:
        # Если не передан user_id, получаем его из профиля
        if not user_id:
            profile_url = 'https://api.avito.ru/core/v1/accounts/self'
            profile_headers = {
                'Authorization': f'Bearer {access_token}'
            }
            profile_response = requests.get(profile_url, headers=profile_headers)
            profile_response.raise_for_status()
            profile_data = profile_response.json()
            user_id = profile_data.get('id')
            
            if not user_id:
                logger.error("Не удалось получить идентификатор пользователя")
                return {"balance_real": 0, "balance_bonus": 0, "advance": 0}
        
        # Получаем реальный баланс кошелька (метод API v1)
        balance_url = f'https://api.avito.ru/core/v1/accounts/{user_id}/balance/'
        balance_headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        balance_response = requests.get(balance_url, headers=balance_headers)
        balance_response.raise_for_status()
        balance_data = balance_response.json()
        
        # Получаем авансы (старый метод API v3)
        advance_url = 'https://api.avito.ru/cpa/v3/balanceInfo'
        advance_headers = {
            'Authorization': f'Bearer {access_token}',
            'X-Source': 'python_script',
            'Content-Type': 'application/json'
        }
        advance_data = {}
        
        advance_response = requests.post(advance_url, headers=advance_headers, json=advance_data)
        advance_response.raise_for_status()
        advance_result = advance_response.json()
        
        # Получаем данные о авансе из ответа API
        advance = 0
        if 'balance' in advance_result:
            advance = advance_result['balance'] / 100
        elif 'data' in advance_result and 'balance' in advance_result['data']:
            advance = advance_result['data']['balance'] / 100
        
        # Формируем ответ с полной информацией о балансе
        return {
            "balance_real": balance_data.get('real', 0),  # Реальные деньги
            "balance_bonus": balance_data.get('bonus', 0),  # Бонусы
            "advance": advance  # Авансовые платежи (старый 'balance')
        }
    except Exception as e:
        logger.error(f"Ошибка при получении информации о балансе: {e}")
        return {"balance_real": 0, "balance_bonus": 0, "advance": 0}

# Оставляем старую функцию для обратной совместимости, но теперь она возвращает авансы
def get_user_ballance(access_token):
    """Устаревшая функция, возвращает авансовые платежи для обратной совместимости"""
    try:
        balance_info = get_user_balance_info(access_token)
        return balance_info['advance']
    except Exception as e:
        logger.error(f"Ошибка при получении аванса: {e}")
        return 0
    
def get_user_info(access_token):
    """
    Получает информацию об авторизованном пользователе.
    
    Args:
        access_token: Токен доступа к API
        
    Returns:
        dict: Словарь с информацией о пользователе (id, email, name, phone и т.д.)
              или пустой словарь в случае ошибки
    """
    try:
        # URL для получения информации о пользователе
        user_info_url = 'https://api.avito.ru/core/v1/accounts/self'
        
        # Заголовки запроса
        headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        logger.info("Запрос информации о пользователе")
        
        # Выполняем запрос
        response = requests.get(user_info_url, headers=headers)
        response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if not response.text.strip():
            logger.error("Получен пустой ответ от API информации о пользователе")
            return {}
            
        # Парсим JSON ответ
        try:
            user_data = response.json()
            logger.info(f"Получена информация о пользователе с ID: {user_data.get('id')}")
            return user_data
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}, содержимое ответа: {response.text}")
            return {}
            
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пользователе: {e}")
        return {}

def get_user_chats(access_token, date_from=None, date_to=None, unread_only=False, chat_types=None, limit=100, offset=0):
    """Получение списка чатов пользователя за определенный период"""
    # Получаем user_id из профиля пользователя
    try:
        user_info = get_user_info(access_token)
        user_id = user_info.get('id')
        
        if not user_id:
            logger.error("Не удалось получить идентификатор пользователя")
            return 0
            
        # Формируем URL для получения чатов
        chats_url = f'https://api.avito.ru/messenger/v2/accounts/{user_id}/chats'
        
        # Параметры запроса (API принимает максимум 100)
        params = {
            'limit': min(limit, 100),  # Ограничиваем до 100
            'offset': offset
        }
        
        # Не передаем даты в параметры URL - они не поддерживаются API
        # Будем фильтровать чаты по датам в коде после получения
        
        # Добавляем необязательные параметры, если они указаны
        if unread_only:
            params['unread_only'] = 'true'
            
        if chat_types:
            if isinstance(chat_types, list):
                params['chat_types'] = ','.join(chat_types)
            else:
                params['chat_types'] = 'u2i'  # По умолчанию только чаты по объявлениям
        
        # Заголовки запроса
        headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        logger.info(f"Запрос чатов пользователя {user_id} с параметрами: {params}")
        
        # Выполняем запрос
        chats_response = requests.get(chats_url, headers=headers, params=params)
        chats_response.raise_for_status()
        chats_result = chats_response.json()
        
        # Получаем все чаты из первой страницы
        all_chats = chats_result.get('chats', [])
        total_count = chats_result.get('count', 0)
        
        # Если нужно получить больше чатов и есть пагинация
        if total_count > 100 and limit > 100:
            # Определяем сколько еще страниц нужно запросить
            max_pages = min(10, (limit // 100) + (1 if limit % 100 > 0 else 0))
            
            for page in range(1, max_pages):
                page_offset = page * 100
                
                params['offset'] = page_offset
                page_response = requests.get(chats_url, headers=headers, params=params)
                
                if page_response.status_code != 200:
                    break
                    
                page_result = page_response.json()
                page_chats = page_result.get('chats', [])
                
                if not page_chats:
                    break
                    
                all_chats.extend(page_chats)
                
                # Если получили нужное количество или все чаты
                if len(all_chats) >= limit or len(all_chats) >= total_count:
                    break
        
        # Фильтруем чаты по дате, если указаны даты
        filtered_chats = all_chats
        if date_from or date_to:
            filtered_chats = []
            from_date = None
            to_date = None
            
            if date_from:
                from_date = datetime.datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            if date_to:
                to_date = datetime.datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            
            for chat in all_chats:
                last_message_time = chat.get('lastMessageTime')
                if last_message_time:
                    message_time = datetime.datetime.fromisoformat(last_message_time.replace('Z', '+00:00'))
                    
                    if from_date and message_time < from_date:
                        continue
                    if to_date and message_time > to_date:
                        continue
                        
                    filtered_chats.append(chat)
        
        # Возвращаем количество чатов
        total_chats = len(filtered_chats)
        logger.info(f"Получено {total_chats} чатов из {len(all_chats)} общих (всего в API: {total_count})")
        return total_chats
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка чатов: {e}")
        return 0

def get_chats_by_time(access_token, date_from=None):
    """
    Получение новых чатов после указанной даты
    
    Args:
        access_token: Токен доступа к API
        date_from: Время, с которого нужно начинать поиск чатов (RFC3339)
                  Если не передано, берется начало текущего дня/недели
    
    Returns:
        int: Количество новых чатов
    """
    try:
        # Если начальная дата не передана, используем текущую дату
        if date_from is None:
            current_time = datetime.datetime.now()
            date_from = current_time.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Получаем информацию о пользователе для получения user_id
        user_info = get_user_info(access_token)
        user_id = user_info.get('id')
        
        if not user_id:
            logger.error("Не удалось получить идентификатор пользователя")
            return 0
        
        # Получаем чаты пользователя через функцию get_user_chats
        # Передаем date_from как параметр для фильтрации
        total_chats = get_user_chats(
            access_token=access_token,
            date_from=date_from,
            chat_types='u2i'
        )
        
        logger.info(f"Найдено {total_chats} чатов после {date_from}")
        return total_chats
            
    except Exception as e:
        logger.error(f"Ошибка при получении новых чатов: {e}")
        return 0

def get_all_numbers(access_token, date_from=None, date_to=None):
    """Получение статистики показов телефона за указанный период"""
    try:
        if date_from is None:
            current_time = datetime.datetime.now()
            date_from = (current_time - datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        if date_to is None:
            date_to = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        phones_url = 'https://api.avito.ru/cpa/v1/phonesInfoFromChats'
        phones_data = {
            'dateTimeFrom': date_from,
            'dateTimeTo': date_to,
            'limit': 100,
            'offset': 0
        }
        phones_headers = {
            'Authorization': f'Bearer {access_token}',
            'X-Source': 'python_script',
            'Content-Type': 'application/json'
        }

        logger.info(f"Запрос статистики показов телефона с {date_from} по {date_to}")
        
        phones_response = requests.post(phones_url, headers=phones_headers, json=phones_data)
        phones_response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if not phones_response.text.strip():
            logger.warning("Получен пустой ответ от API показов телефона")
            return 0
        
        try:
            phones_result = phones_response.json()
            total_phone_results = phones_result.get('total', 0)
            logger.info(f"Получено {total_phone_results} показов телефона")
            return total_phone_results
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}, содержимое ответа: {phones_response.text[:200]}")
            return 0
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к API показов телефона: {e}")
        return 0
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении показов телефона: {e}")
        return 0


def get_user_items_stats(access_token, user_id, status="active", per_page=25, page=1, date_from=None, date_to=None, period_grouping="day"):
    """Получает базовую информацию о объявлениях пользователя и их идентификаторы."""
    try:
        items_url = 'https://api.avito.ru/core/v1/items'
        items_headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        params = {
            'status': status,
            'per_page': per_page,
            'page': page
        }
        
        logger.info(f"Запрос информации об объявлениях пользователя {user_id}")
        
        response = requests.get(items_url, headers=items_headers, params=params)
        response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if not response.text.strip():
            logger.warning("Получен пустой ответ от API объявлений")
            return []
        
        try:
            result = response.json()
            
            # Правильное извлечение идентификаторов объявлений из структуры ответа API
            items = result.get('resources', [])
            item_ids = [item['id'] for item in items if 'id' in item]
            
            logger.info(f"Получено {len(item_ids)} идентификаторов объявлений")
            return item_ids
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}, содержимое ответа: {response.text[:200]}")
            return []
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к API объявлений: {e}")
        return []
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении объявлений: {e}")
        return []

def get_item_promotion_info(access_token, user_id, item_ids):
    """Получает информацию о продвижении объявлений."""
    try:
        if not item_ids:
            logger.info("Нет объявлений для анализа продвижения")
            return {"total_items": 0, "xl_promotion_count": 0, "tools_subscription_count": 0}
    
        # Подсчет объявлений с XL продвижением и другими услугами
        xl_promotion_count = 0
        tools_subscription_count = 0
        
        # Ограничиваем количество проверяемых объявлений
        check_ids = item_ids[:50]  # Проверяем не более 50 объявлений
        
        # Получаем детальную информацию о каждом объявлении для проверки продвижений
        for item_id in check_ids:
            try:
                item_info_url = f'https://api.avito.ru/core/v1/accounts/{user_id}/items/{item_id}/'
                item_info_headers = {
                    'Authorization': f'Bearer {access_token}'
                }
                
                item_response = requests.get(item_info_url, headers=item_info_headers)
                item_response.raise_for_status()
                
                # Проверяем, что ответ не пустой
                if not item_response.text.strip():
                    continue
                    
                item_data = item_response.json()
                
                # Проверка наличия XL продвижения и других услуг
                services = item_data.get('services', [])
                has_xl = False
                has_tools_subscription = False
                
                for service in services:
                    service_code = service.get('code')
                    if service_code == 'xl':
                        has_xl = True
                    elif service_code in ['vip', 'highlight', 'pushup', 'premium']:
                        has_tools_subscription = True
                
                # Подсчитываем объявления
                if has_xl:
                    xl_promotion_count += 1
                if has_tools_subscription:
                    tools_subscription_count += 1
                        
            except Exception as e:
                logger.error(f"Ошибка при получении информации о продвижении объявления {item_id}: {e}")
                continue
        
        # Если проверили не все объявления, экстраполируем результаты
        if len(check_ids) < len(item_ids):
            ratio = len(item_ids) / len(check_ids)
            xl_promotion_count = int(xl_promotion_count * ratio)
            tools_subscription_count = int(tools_subscription_count * ratio)
            logger.info(f"Экстраполяция данных по продвижению: проверено {len(check_ids)} из {len(item_ids)} объявлений")
        
        result = {
            "total_items": len(item_ids),
            "xl_promotion_count": xl_promotion_count,
            "tools_subscription_count": tools_subscription_count
        }
        
        logger.info(f"Информация о продвижениях: всего {len(item_ids)} объявлений, с XL продвижением: {xl_promotion_count}, с подпиской на инструменты: {tools_subscription_count}")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при получении информации о продвижении объявлений: {e}")
        return {
            "total_items": len(item_ids) if item_ids else 0,
            "xl_promotion_count": 0,
            "tools_subscription_count": 0
        }

def get_items_statistics(access_token, user_id, item_ids, date_from=None, date_to=None, period_grouping="day"):
    """Получает статистику по объявлениям: просмотры, контакты, избранное."""
    try:
        if not item_ids:
            logger.info("Нет объявлений для получения статистики")
            return {
                "total_views": 0,
                "total_contacts": 0,
                "total_favorites": 0
            }
        
        if date_from is None:
            current_time = datetime.datetime.now()
            date_from = (current_time - datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            
        if date_to is None:
            date_to = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            
        # Получение статистики по объявлениям
        stats_url = f'https://api.avito.ru/stats/v1/accounts/{user_id}/items'
        stats_headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Ограничиваем количество ID для запроса
        request_ids = item_ids[:200]  # API ограничение
        
        stats_data = {
            'dateFrom': date_from,
            'dateTo': date_to,
            'itemIds': request_ids,
            'fields': ["uniqViews", "uniqContacts", "uniqFavorites"],
            'periodGrouping': period_grouping
        }
        
        logger.info(f"Запрос статистики по {len(request_ids)} объявлениям с {date_from} по {date_to}")
        
        stats_response = requests.post(stats_url, headers=stats_headers, json=stats_data)
        stats_response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if not stats_response.text.strip():
            logger.warning("Получен пустой ответ от API статистики объявлений")
            return {
                "total_views": 0,
                "total_contacts": 0,
                "total_favorites": 0
            }
        
        try:
            stats_result = stats_response.json()
            
            # Подсчет общего количества просмотров, контактов и избранных
            total_views = 0
            total_contacts = 0
            total_favorites = 0
            
            for item in stats_result.get('result', {}).get('items', []):
                for stat in item.get('stats', []):
                    total_views += stat.get('uniqViews', 0)
                    total_contacts += stat.get('uniqContacts', 0)
                    total_favorites += stat.get('uniqFavorites', 0)
            
            # Если запросили не все объявления, экстраполируем результаты
            if len(request_ids) < len(item_ids):
                ratio = len(item_ids) / len(request_ids)
                total_views = int(total_views * ratio)
                total_contacts = int(total_contacts * ratio)
                total_favorites = int(total_favorites * ratio)
                logger.info(f"Экстраполяция статистики: проверено {len(request_ids)} из {len(item_ids)} объявлений")
            
            result = {
                "total_views": total_views,
                "total_contacts": total_contacts,
                "total_favorites": total_favorites
            }
            
            logger.info(f"Статистика объявлений: просмотры: {total_views}, контакты: {total_contacts}, избранное: {total_favorites}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}, содержимое ответа: {stats_response.text[:200]}")
            return {
                "total_views": 0,
                "total_contacts": 0,
                "total_favorites": 0
            }
            
    except Exception as e:
        logger.error(f"Ошибка при получении статистики объявлений: {e}")
        return {
            "total_views": 0,
            "total_contacts": 0,
            "total_favorites": 0
        }


def get_user_rating_info(access_token):
    """Получение рейтинга пользователя"""
    try:
        rating_info_url = 'https://api.avito.ru/ratings/v1/info'
        rating_info_headers = {
            'Authorization': f'Bearer {access_token}'
        }

        logger.info("Запрос информации о рейтинге пользователя")
        
        response = requests.get(rating_info_url, headers=rating_info_headers)
        response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if not response.text.strip():
            logger.warning("Получен пустой ответ от API рейтинга")
            return 0
        
        try:
            result = response.json()
            score = result.get('rating', {}).get('score', 0)
            logger.info(f"Получен рейтинг пользователя: {score}")
            return score
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}, содержимое ответа: {response.text[:200]}")
            return 0
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к API рейтинга: {e}")
        return 0
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении рейтинга: {e}")
        return 0


def get_user_reviews(access_token, date_from=None, date_to=None, offset=0, limit=50):
    """Получение отзывов пользователя за указанный период"""
    try:
        reviews_url = 'https://api.avito.ru/ratings/v1/reviews'
        reviews_headers = {
            'Authorization': f'Bearer {access_token}'
        }

        params = {
            'offset': offset,
            'limit': limit
        }

        logger.info(f"Запрос отзывов пользователя с {date_from} по {date_to}")
        
        response = requests.get(reviews_url, headers=reviews_headers, params=params)
        response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if not response.text.strip():
            logger.warning("Получен пустой ответ от API отзывов")
            return {"total_reviews": 0, "period_reviews": 0}
        
        try:
            result = response.json()
            total_reviews = result.get('total', 0)
            reviews = result.get('reviews', [])

            # Подсчет отзывов за указанный период
            period_reviews = 0

            # Определяем временной промежуток для фильтрации
            if date_from is None:
                today = datetime.datetime.now().date()
                for review in reviews:
                    created_at = review.get('createdAt', 0)
                    if created_at:
                        review_date = datetime.datetime.fromtimestamp(created_at).date()
                        if review_date == today:
                            period_reviews += 1
            else:
                # Преобразуем строковые даты в объекты datetime для сравнения
                date_from_obj = datetime.datetime.fromisoformat(date_from.split('T')[0]).date()
                date_to_obj = datetime.datetime.fromisoformat(date_to.split('T')[0]).date() if date_to else datetime.datetime.now().date()
                
                for review in reviews:
                    created_at = review.get('createdAt', 0)
                    if created_at:
                        review_date = datetime.datetime.fromtimestamp(created_at).date()
                        if date_from_obj <= review_date <= date_to_obj:
                            period_reviews += 1

            logger.info(f"Получено отзывов: всего {total_reviews}, за период: {period_reviews}")
            return {
                "total_reviews": total_reviews,
                "period_reviews": period_reviews
            }
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}, содержимое ответа: {response.text[:200]}")
            return {"total_reviews": 0, "period_reviews": 0}
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к API отзывов: {e}")
        return {"total_reviews": 0, "period_reviews": 0}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении отзывов: {e}")
        return {"total_reviews": 0, "period_reviews": 0}





def get_avito_user_id(client_id, client_secret):
    token_url = 'https://api.avito.ru/token'
    token_data = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret
    }
    
    try:
        # Получаем токен доступа
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        token_result = token_response.json()
        access_token = token_result.get('access_token')
        
        if not access_token:
            return None
            
        # Получаем информацию о пользователе
        user_info_url = 'https://api.avito.ru/core/v1/accounts/self'
        user_info_headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        user_response = requests.get(user_info_url, headers=user_info_headers)
        user_response.raise_for_status()
        user_data = user_response.json()
        
        # Возвращаем Avito ID пользователя
        return user_data.get('id')
    except Exception as e:
        print(f"Ошибка при получении Avito ID: {e}")
        return None



def get_daily_statistics(client_id, client_secret):
    try:
        # Получаем текущую дату и вчерашнюю дату
        current_time = datetime.datetime.now()
        yesterday = current_time - datetime.timedelta(days=1)
        yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Форматы дат для разных API
        yesterday_date = yesterday.strftime("%Y-%m-%d")
        
        logger.info(f"Запрос дневной статистики за {yesterday_date}")
        
        # Получаем токен доступа
        access_token = get_access_token(client_id, client_secret)
        if not access_token:
            logger.error("Не удалось получить токен доступа")
            raise Exception("Не удалось получить токен доступа")
            
        user_id = get_avito_user_id(client_id, client_secret)
        if not user_id:
            logger.error("Не удалось получить ID пользователя")
            raise Exception("Не удалось получить ID пользователя")
        
        # Инициализируем значения по умолчанию
        total_calls = 0
        missed_calls = 0
        balance_info = {"balance_real": 0, "balance_bonus": 0, "advance": 0}
        expenses_info = {"total": 0, "details": {}}
        total_chats = 0
        new_chats = 0
        total_phones = 0
        rating = 0
        reviews_info = {"total_reviews": 0, "period_reviews": 0}
        promotion_info = {"total_items": 0, "xl_promotion_count": 0, "tools_subscription_count": 0}
        items_stats = {"total_views": 0, "total_contacts": 0, "total_favorites": 0}
        
        # Создаем ключ для кэша статистики
        stats_cache_key = f"daily_stats_{user_id}_{yesterday_date}"
        
        # Проверяем, есть ли у нас кэшированные данные
        if hasattr(get_daily_statistics, '_stats_cache') and stats_cache_key in get_daily_statistics._stats_cache:
            cache_data, cache_time = get_daily_statistics._stats_cache[stats_cache_key]
            time_diff = (current_time - cache_time).total_seconds() / 60  # Разница в минутах
            
            # Используем кэш, если он не старше 30 минут
            if time_diff < 30:
                logger.info(f"Использование кэшированной дневной статистики ({time_diff:.1f} минут)")
                return cache_data
        
        # Пытаемся получить расширенную статистику профиля, только если не было ошибок ранее
        use_profile_stats = True
        if hasattr(get_daily_statistics, '_profile_stats_errors'):
            # Если было слишком много ошибок (429) в течение последнего часа, не запрашиваем API
            last_error_time, error_count = get_daily_statistics._profile_stats_errors
            if (current_time - last_error_time).total_seconds() < 3600 and error_count > 3:
                logger.warning("Пропуск запроса к API статистики из-за предыдущих ошибок (Too Many Requests)")
                use_profile_stats = False
        else:
            get_daily_statistics._profile_stats_errors = (datetime.datetime.min, 0)
        
        profile_stats = {}
        if use_profile_stats:
            # Получаем расширенную статистику профиля за вчерашний день
            profile_stats = get_profile_statistics(access_token, user_id, date_from=yesterday_date, date_to=yesterday_date)
        
        # Если статистика успешно получена, используем ее
        if not profile_stats is None:
            # Используем статистику профиля для звонков и чатов
            total_calls = profile_stats.get('calls', 0)
            total_chats = profile_stats.get('chats', 0)
            
            # Обновляем статистику объявлений
            items_stats = {
                "total_views": profile_stats.get('views', 0),
                "total_contacts": profile_stats.get('contacts', 0),
                "total_favorites": profile_stats.get('favorites', 0)
            }
            
            # Обновляем расходы
            spending = profile_stats.get('spending', {})
            if spending:
                expenses_info = {
                    "total": spending.get('total', 0),
                    "details": {
                        "presence": {
                            "amount": spending.get('presence', 0),
                            "count": 1,
                            "type": "размещение",
                            "items": []
                        },
                        "promo": {
                            "amount": spending.get('promo', 0),
                            "count": 1,
                            "type": "продвижение",
                            "items": []
                        },
                        "sales": {
                            "amount": spending.get('sales', 0),
                            "count": 1,
                            "type": "продвижение",
                            "items": []
                        }
                    }
                }
            
            # Обновляем информацию о количестве объявлений
            # Получаем правильное количество объявлений через API
            try:
                total_items = get_total_items_count(access_token, status="active")
                promotion_info["total_items"] = total_items
            except Exception as e:
                logger.error(f"Ошибка при получении количества объявлений: {e}")
                promotion_info["total_items"] = profile_stats.get('active_items', 0)  # Fallback
            
            # Сбрасываем счетчик ошибок
            get_daily_statistics._profile_stats_errors = (datetime.datetime.min, 0)
        else:
            # Если получили ошибку 429, обновляем счетчик ошибок
            if hasattr(get_profile_statistics, 'last_error_code') and get_profile_statistics.last_error_code == 429:
                last_error_time, error_count = get_daily_statistics._profile_stats_errors
                if (current_time - last_error_time).total_seconds() > 3600:
                    # Если последняя ошибка была больше часа назад, сбрасываем счетчик
                    get_daily_statistics._profile_stats_errors = (current_time, 1)
                else:
                    # Увеличиваем счетчик ошибок
                    get_daily_statistics._profile_stats_errors = (last_error_time, error_count + 1)
                
                logger.warning(f"Зарегистрирована ошибка API статистики (429), всего: {error_count + 1} за последний час")
            
            # Если расширенная статистика недоступна, используем старые методы
            try:
                # Получаем статистику звонков за вчерашний день
                total_calls = get_total_calls(access_token, yesterday_start, yesterday_end)
                missed_calls = get_missed_calls(access_token, yesterday_start, yesterday_end)
            except Exception as e:
                logger.error(f"Ошибка при получении статистики звонков: {e}")
            
            try:
                # Получаем чаты за вчерашний день
                total_chats = get_user_chats(access_token, yesterday_start, yesterday_end)
            except Exception as e:
                logger.error(f"Ошибка при получении информации о чатах: {e}")
                
            try:
                # Получаем информацию о объявлениях за вчерашний день
                # Получаем общее количество активных объявлений
                total_items = get_total_items_count(access_token, status="active")
                
                # Получаем ID объявлений для статистики и продвижения (ограниченное количество)
                item_ids = get_user_items_stats(access_token, user_id, status="active", per_page=100)
                items_stats = get_items_statistics(access_token, user_id, item_ids, date_from=yesterday_start, date_to=yesterday_end)
                
                # Получаем информацию о продвижении, но используем правильное общее количество
                promotion_info = get_item_promotion_info(access_token, user_id, item_ids)
                promotion_info["total_items"] = total_items  # Заменяем на правильное количество
            except Exception as e:
                logger.error(f"Ошибка при получении информации об объявлениях: {e}")
                
            try:
                # Получаем информацию о расходах за вчерашний день
                expenses_info = get_operations_history(access_token, yesterday_start, yesterday_end)
            except Exception as e:
                logger.error(f"Ошибка при получении информации о расходах: {e}")
        
        # Дополняем данные, которые нельзя получить из расширенной статистики
        try:
            # Если статистика профиля не вернула пропущенные звонки, получаем их отдельно
            if missed_calls == 0 and total_calls > 0:
                missed_calls = get_missed_calls(access_token, yesterday_start, yesterday_end)
        except Exception as e:
            logger.error(f"Ошибка при получении информации о пропущенных звонках: {e}")
            
        try:
            # Получаем новые чаты за период (функция использует фильтрацию по дате)
            new_chats = get_chats_by_time(access_token, yesterday_start)
            total_phones = get_all_numbers(access_token, yesterday_start, yesterday_end)
        except Exception as e:
            logger.error(f"Ошибка при получении дополнительной информации о чатах и телефонах: {e}")
        
        try:
            # Получаем полную информацию о балансе (текущую)
            balance_info = get_user_balance_info(access_token, user_id)
        except Exception as e:
            logger.error(f"Ошибка при получении информации о балансе: {e}")
        
        try:
            # Получаем CPA баланс
            cpa_balance = get_cpa_balance(access_token)
        except Exception as e:
            logger.error(f"Ошибка при получении CPA баланса: {e}")
            cpa_balance = 0
        
        try:
            # Получаем рейтинг и отзывы
            rating = get_user_rating_info(access_token)
            reviews_info = get_user_reviews(access_token, yesterday_start, yesterday_end)
        except Exception as e:
            logger.error(f"Ошибка при получении информации о рейтинге и отзывах: {e}")
        
        # Формируем и возвращаем полную статистику за вчерашний день
        result = {
            "date": yesterday_date,
            "calls": {
                "total": total_calls,
                "missed": missed_calls,
                "answered": total_calls - missed_calls
            },
            "balance_real": balance_info["balance_real"],
            "balance_bonus": balance_info["balance_bonus"],
            "advance": balance_info["advance"],
            "cpa_balance": cpa_balance,
            "expenses": expenses_info,
            "chats": {
                "total": total_chats,
                "new": new_chats
            },
            "phones_received": total_phones,
            "rating": rating,
            "reviews": {
                "total": reviews_info["total_reviews"],
                "today": reviews_info["period_reviews"]
            },
            "items": {
                "total": promotion_info["total_items"],
                "with_xl_promotion": promotion_info["xl_promotion_count"],
                "with_tools_subscription": promotion_info["tools_subscription_count"]
            },
            "statistics": {
                "views": items_stats["total_views"],
                "contacts": items_stats["total_contacts"],
                "favorites": items_stats["total_favorites"]
            }
        }
        
        # Сохраняем результат в кэш
        if not hasattr(get_daily_statistics, '_stats_cache'):
            get_daily_statistics._stats_cache = {}
        get_daily_statistics._stats_cache[stats_cache_key] = (result, current_time)
        
        logger.info(f"Дневная статистика за вчера успешно получена")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при получении дневной статистики: {e}")
        # Возвращаем структуру с нулевыми значениями в случае ошибки
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        return {
            "date": yesterday,
            "calls": {"total": 0, "missed": 0, "answered": 0},
            "balance_real": 0,
            "balance_bonus": 0,
            "advance": 0,
            "cpa_balance": 0,
            "expenses": {"total": 0, "details": {}},
            "chats": {"total": 0, "new": 0},
            "phones_received": 0,
            "rating": 0,
            "reviews": {"total": 0, "today": 0},
            "items": {"total": 0, "with_xl_promotion": 0, "with_tools_subscription": 0},
            "statistics": {"views": 0, "contacts": 0, "favorites": 0}
        }


def get_weekly_statistics(client_id, client_secret):
    try:
        # Получаем текущую дату
        current_time = datetime.datetime.now()
        
        # Определяем прошлую неделю (понедельник-воскресенье)
        # Сначала находим понедельник текущей недели
        days_since_monday = current_time.weekday()  # 0 = понедельник, 6 = воскресенье
        current_monday = current_time - datetime.timedelta(days=days_since_monday)
        
        # Прошлый понедельник (начало прошлой недели)
        last_monday = current_monday - datetime.timedelta(weeks=1)
        
        # Прошлое воскресенье (конец прошлой недели)
        last_sunday = last_monday + datetime.timedelta(days=6)
        
        # Форматируем даты для API
        week_start = last_monday.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        week_end = last_sunday.replace(hour=23, minute=59, second=59, microsecond=999999).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Форматы дат для разных API
        week_start_date = last_monday.strftime("%Y-%m-%d")
        week_end_date = last_sunday.strftime("%Y-%m-%d")
        
        logger.info(f"Запрос недельной статистики за прошлую неделю с {week_start_date} по {week_end_date}")
        
        # Создаем ключ для кэша статистики
        stats_cache_key = f"weekly_stats_{week_start_date}_{week_end_date}"
        
        # Проверяем, есть ли у нас кэшированные данные
        if hasattr(get_weekly_statistics, '_stats_cache') and stats_cache_key in get_weekly_statistics._stats_cache:
            cache_data, cache_time = get_weekly_statistics._stats_cache[stats_cache_key]
            time_diff = (current_time - cache_time).total_seconds() / 60  # Разница в минутах
            
            # Используем кэш, если он не старше 60 минут
            if time_diff < 60:
                logger.info(f"Использование кэшированной недельной статистики ({time_diff:.1f} минут)")
                return cache_data
        
        # Получаем токен доступа
        access_token = get_access_token(client_id, client_secret)
        if not access_token:
            logger.error("Не удалось получить токен доступа")
            raise Exception("Не удалось получить токен доступа")
            
        user_id = get_avito_user_id(client_id, client_secret)
        if not user_id:
            logger.error("Не удалось получить ID пользователя")
            raise Exception("Не удалось получить ID пользователя")
        
        # Инициализируем значения по умолчанию
        total_calls = 0
        missed_calls = 0
        balance_info = {"balance_real": 0, "balance_bonus": 0, "advance": 0}
        expenses_info = {"total": 0, "details": {}}
        total_chats = 0
        new_chats = 0
        total_phones = 0
        rating = 0
        reviews_info = {"total_reviews": 0, "period_reviews": 0}
        promotion_info = {"total_items": 0, "xl_promotion_count": 0, "tools_subscription_count": 0}
        items_stats = {"total_views": 0, "total_contacts": 0, "total_favorites": 0}
        
        # Пытаемся получить расширенную статистику профиля, только если не было ошибок ранее
        use_profile_stats = True
        if hasattr(get_daily_statistics, '_profile_stats_errors'):
            # Проверяем, были ли ошибки в дневной статистике
            last_error_time, error_count = get_daily_statistics._profile_stats_errors
            if (current_time - last_error_time).total_seconds() < 3600 and error_count > 3:
                logger.warning("Пропуск запроса к API статистики из-за предыдущих ошибок (Too Many Requests)")
                use_profile_stats = False
        
        profile_stats = {}
        if use_profile_stats:
            # Получаем расширенную статистику профиля
            profile_stats = get_profile_statistics(access_token, user_id, date_from=week_start_date, date_to=week_end_date)
        # Если статистика успешно получена, используем ее
        if not profile_stats is None:
            # Используем статистику профиля для звонков и чатов
            total_calls = profile_stats.get('calls', 0)
            total_chats = profile_stats.get('chats', 0)
            
            # Обновляем статистику объявлений
            items_stats = {
                "total_views": profile_stats.get('views', 0),
                "total_contacts": profile_stats.get('contacts', 0),
                "total_favorites": profile_stats.get('favorites', 0)
            }
            
            # Обновляем расходы
            spending = profile_stats.get('spending', {})
            if spending:
                expenses_info = {
                    "total": spending.get('total', 0),
                    "details": {
                        "presence": {
                            "amount": spending.get('presence', 0),
                            "count": 1,
                            "type": "размещение",
                            "items": []
                        },
                        "promo": {
                            "amount": spending.get('promo', 0),
                            "count": 1,
                            "type": "продвижение",
                            "items": []
                        },
                        "sales": {
                            "amount": spending.get('sales', 0),
                            "count": 1,
                            "type": "продвижение",
                            "items": []
                        }
                    }
                }
            
            # Обновляем информацию о количестве объявлений
            # Получаем правильное количество объявлений через API
            try:
                total_items = get_total_items_count(access_token, status="active")
                promotion_info["total_items"] = total_items
            except Exception as e:
                logger.error(f"Ошибка при получении количества объявлений: {e}")
                promotion_info["total_items"] = profile_stats.get('active_items', 0)  # Fallback
        else:
            # Если расширенная статистика недоступна, используем старые методы
            try:
                # Получаем статистику звонков
                total_calls = get_total_calls(access_token, week_start, week_end)
                missed_calls = get_missed_calls(access_token, week_start, week_end)
            except Exception as e:
                logger.error(f"Ошибка при получении статистики звонков: {e}")
                
            try:
                # Получаем чаты
                total_chats = get_user_chats(access_token, week_start, week_end)
            except Exception as e:
                logger.error(f"Ошибка при получении информации о чатах: {e}")
                
            try:
                # Получаем информацию о объявлениях
                # Получаем общее количество активных объявлений
                total_items = get_total_items_count(access_token, status="active")
                
                # Получаем ID объявлений для статистики и продвижения (ограниченное количество)
                item_ids = get_user_items_stats(access_token, user_id, status="active", per_page=100)
                items_stats = get_items_statistics(access_token, user_id, item_ids, date_from=week_start, date_to=week_end)
                
                # Получаем информацию о продвижении, но используем правильное общее количество
                promotion_info = get_item_promotion_info(access_token, user_id, item_ids)
                promotion_info["total_items"] = total_items  # Заменяем на правильное количество
            except Exception as e:
                logger.error(f"Ошибка при получении информации об объявлениях: {e}")
                
            # try:
            #     get_operations_history
            #     # Получаем информацию о расходах
            #     # expenses_info = get_operations_history(access_token, week_start, week_end)
            #     expenses_info = {
            #         "total": spending.get("total", 0),
            #         "details": {
            #             "promo": spending['details'].get()
            #         }
            #     }
            # except Exception as e:
            #     logger.error(f"Ошибка при получении информации о расходах: {e}")
        
        # Дополняем данные, которые нельзя получить из расширенной статистики
        try:
            # Если статистика профиля не вернула пропущенные звонки, получаем их отдельно
            if missed_calls == 0 and total_calls > 0:
                missed_calls = get_missed_calls(access_token, week_start, week_end)
        except Exception as e:
            logger.error(f"Ошибка при получении информации о пропущенных звонках: {e}")
            
        try:
            # Получаем новые чаты за период
            new_chats = get_chats_by_time(access_token, week_start)
            total_phones = get_all_numbers(access_token, week_start, week_end)
        except Exception as e:
            logger.error(f"Ошибка при получении дополнительной информации о чатах и телефонах: {e}")
        
        try:
            # Получаем полную информацию о балансе
            balance_info = get_user_balance_info(access_token, user_id)
        except Exception as e:
            logger.error(f"Ошибка при получении информации о балансе: {e}")
        
        try:
            # Получаем CPA баланс
            cpa_balance = get_cpa_balance(access_token)
        except Exception as e:
            logger.error(f"Ошибка при получении CPA баланса: {e}")
            cpa_balance = 0
        
        try:
            # Получаем рейтинг и отзывы
            rating = get_user_rating_info(access_token)
            reviews_info = get_user_reviews(access_token, week_start, week_end)
        except Exception as e:
            logger.error(f"Ошибка при получении информации о рейтинге и отзывах: {e}")
        
        # Формируем и возвращаем полную статистику за прошлую неделю
        result = {
            "period": f"{last_monday.strftime('%Y-%m-%d')} - {last_sunday.strftime('%Y-%m-%d')}",
            "calls": {
                "total": total_calls,
                "missed": missed_calls,
                "answered": total_calls - missed_calls
            },
            "balance_real": balance_info["balance_real"],
            "balance_bonus": balance_info["balance_bonus"],
            "advance": balance_info["advance"],
            "cpa_balance": cpa_balance,
            "expenses": expenses_info,
            "chats": {
                "total": total_chats,
                "new": new_chats
            },
            "phones_received": total_phones,
            "rating": rating,
            "reviews": {
                "total": reviews_info["total_reviews"],
                "weekly": reviews_info["period_reviews"]
            },
            "items": {
                "total": promotion_info["total_items"],
                "with_xl_promotion": promotion_info["xl_promotion_count"],
                "with_tools_subscription": promotion_info["tools_subscription_count"]
            },
            "statistics": {
                "views": items_stats["total_views"],
                "contacts": items_stats["total_contacts"],
                "favorites": items_stats["total_favorites"]
            }
        }
        
        # Сохраняем результат в кэш
        if not hasattr(get_weekly_statistics, '_stats_cache'):
            get_weekly_statistics._stats_cache = {}
        get_weekly_statistics._stats_cache[stats_cache_key] = (result, current_time)
        
        logger.info(f"Недельная статистика за прошлую неделю успешно получена")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при получении недельной статистики: {e}")
        # Возвращаем структуру с нулевыми значениями в случае ошибки
        current_time = datetime.datetime.now()
        days_since_monday = current_time.weekday()
        current_monday = current_time - datetime.timedelta(days=days_since_monday)
        last_monday = current_monday - datetime.timedelta(weeks=1)
        last_sunday = last_monday + datetime.timedelta(days=6)
        
        return {
            "period": f"{last_monday.strftime('%Y-%m-%d')} - {last_sunday.strftime('%Y-%m-%d')}",
            "calls": {"total": 0, "missed": 0, "answered": 0},
            "balance_real": 0,
            "balance_bonus": 0,
            "advance": 0,
            "cpa_balance": 0,
            "expenses": {"total": 0, "details": {}},
            "chats": {"total": 0, "new": 0},
            "phones_received": 0,
            "rating": 0,
            "reviews": {"total": 0, "weekly": 0},
            "items": {"total": 0, "with_xl_promotion": 0, "with_tools_subscription": 0},
            "statistics": {"views": 0, "contacts": 0, "favorites": 0}
        }

def get_operations_history(access_token, date_from, date_to):
    """
    Получает историю операций пользователя за указанный период
    и возвращает детализацию расходов.
    
    Args:
        access_token: Токен доступа к API
        date_from: Начало периода в формате строки ISO (например, '2023-04-01T00:00:00Z')
        date_to: Конец периода в формате строки ISO (например, '2023-04-08T00:00:00Z')
        
    Returns:
        dict: Словарь с общей суммой расходов и детализацией по типам услуг
    """
    try:
        # URL для получения истории операций
        operations_url = 'https://api.avito.ru/core/v1/accounts/operations_history/'
        
        # Заголовки запроса
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Данные запроса
        data = {
            'dateTimeFrom': date_from,
            'dateTimeTo': date_to,
            'limit': 1000  # Увеличиваем лимит для получения большего количества операций
        }
        
        logger.info(f"Запрос истории операций с {date_from} по {date_to}")
        
        # Выполняем запрос
        response = requests.post(operations_url, headers=headers, json=data)
        response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if not response.text.strip():
            logger.error("Получен пустой ответ от API операций")
            return {'total': 0, 'details': {}}
            
        # Парсим JSON ответ
        try:
            result = response.json()
            logger.info(f"Получен ответ от API операций с {len(result.get('operations', []))} операциями")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}, содержимое ответа: {response.text}")
            return {'total': 0, 'details': {}}
        
        # Инициализируем счетчики и структуру для детализации расходов
        total_expenses = 0
        expenses_details = {}
        
        # Обрабатываем все операции
        for operation in result.get('operations', []):
            # Тип операции
            operation_type = operation.get('operationType', '')
            
            # Считаем только операции расхода средств
            expense_types = [
                'резервирование средств под услугу',
                'списание за услугу',
                'резервирование средств',
                'списание средств',
                'списание',
                'оплата услуги'
            ]
            
            if operation_type.lower() not in [t.lower() for t in expense_types]:
                continue
                
            # Получаем сумму расхода
            amount_rub = float(operation.get('amountRub', 0))
            if amount_rub <= 0:
                continue
                
            # Добавляем в общую сумму расходов
            total_expenses += amount_rub
            
            # Получаем информацию о типе услуги
            service_name = operation.get('serviceName', 'Неизвестно')
            operation_name = operation.get('operationName', 'Неизвестно')
            service_type = operation.get('serviceType', 'Неизвестно')
            item_id = operation.get('itemId', 'Неизвестно')
            
            # Формируем ключ для группировки
            key = f"{service_name}"
            if service_type and service_type != 'Неизвестно':
                key += f" ({service_type})"
            
            # Добавляем или обновляем запись в детализации
            if key in expenses_details:
                expenses_details[key]['amount'] += amount_rub
                expenses_details[key]['count'] += 1
                if item_id and item_id != 'Неизвестно':
                    expenses_details[key]['items'].add(str(item_id))
            else:
                expenses_details[key] = {
                    'amount': amount_rub,
                    'count': 1,
                    'type': operation_type,
                    'items': {str(item_id)} if item_id and item_id != 'Неизвестно' else set()
                }
        
        # Преобразуем множества объявлений в списки для сериализации JSON
        for key in expenses_details:
            expenses_details[key]['items'] = list(expenses_details[key]['items'])
            if len(expenses_details[key]['items']) == 1 and expenses_details[key]['items'][0] == 'Неизвестно':
                expenses_details[key]['items'] = []
        
        # Формируем структуру с результатами
        result = {
            'total': total_expenses,
            'details': expenses_details
        }
        
        logger.info(f"Расходы за период: общая сумма {total_expenses:.2f} руб., {len(expenses_details)} категорий")
        return result
    except Exception as e:
        logger.error(f"Ошибка при получении истории операций: {e}")
        return {
            'total': 0,
            'details': {}
        }





def get_daily_expenses(access_token):
    """Получает расходы за текущий день"""
    # Получаем текущую дату и начало дня
    current_time = datetime.datetime.now()
    day_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    current_iso = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    logger.info(f"Запрос дневных расходов с {day_start} по {current_iso}")
    
    # Получаем расходы
    return get_operations_history(access_token, day_start, current_iso)

def get_weekly_expenses(access_token):
    """Получает расходы за текущую неделю"""
    # Получаем текущую дату и начало недели (7 дней назад)
    current_time = datetime.datetime.now()
    week_start = (current_time - datetime.timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    current_iso = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    logger.info(f"Запрос недельных расходов с {week_start} по {current_iso}")
    
    # Получаем расходы
    return get_operations_history(access_token, week_start, current_iso)

def get_profile_statistics(access_token, user_id, date_from=None, date_to=None, grouping="totals"):
    """
    Получение расширенной статистики профиля пользователя с использованием API v2
    
    Args:
        access_token: Токен доступа к API
        user_id: ID пользователя
        date_from: Начальная дата в формате YYYY-MM-DD
        date_to: Конечная дата в формате YYYY-MM-DD
        grouping: Тип группировки ('totals', 'day', 'week', 'month', 'item')
        
    Returns:
        dict: Словарь с показателями статистики
    """
    try:
        # Сбрасываем код последней ошибки
        get_profile_statistics.last_error_code = None
        
        # Создаем уникальный ключ для кэширования
        cache_key = f"profile_stats_{user_id}_{date_from}_{date_to}_{grouping}"
        
        # Проверяем, есть ли кэш для этого запроса в глобальном хранилище
        if not hasattr(get_profile_statistics, '_stats_cache'):
            get_profile_statistics._stats_cache = {}
            
        # Проверяем наличие кэша и его актуальность (не старше 1 часа)
        current_time = datetime.datetime.now()
        if cache_key in get_profile_statistics._stats_cache:
            cache_data, cache_time = get_profile_statistics._stats_cache[cache_key]
            time_diff = (current_time - cache_time).total_seconds() / 3600  # Разница в часах
            
            if time_diff < 1:  # Кэш действителен в течение 1 часа
                logger.info(f"Использование кэшированных данных статистики профиля ({time_diff:.2f} часов)")
                return cache_data
        
        # Если даты не указаны, используем текущий день/неделю
        if date_from is None:
            if grouping == "totals":
                # Для общей статистики берем последние 30 дней
                current_time = datetime.datetime.now()
                date_from = (current_time - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
                date_to = current_time.strftime("%Y-%m-%d")
            else:
                # Для детальной статистики берем текущий день
                current_time = datetime.datetime.now()
                date_from = current_time.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d")
                date_to = current_time.strftime("%Y-%m-%d")
        
        if date_to is None:
            date_to = datetime.datetime.now().strftime("%Y-%m-%d")

            
        
        # URL для получения статистики
        stats_url = f'https://api.avito.ru/stats/v2/accounts/{user_id}/items'
        
        # Заголовки запроса
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        offers_url = 'https://api.avito.ru/special-offers/v1/stats'
        offers_states = {
            "dateTimeFrom": f"{date_to}T00:00:00Z",
            "dateTimeTo": f"{date_from}T23:59:59Z",
            }

        offers_response = requests.post(offers_url, headers=headers, json=offers_states)
        offers_sum = 0
        for item in offers_response.json().get('stats', {}):
            offers_sum += item['price']
        
        # Набор всех нужных метрик
        metrics = [
            "views",              # Просмотры
            "contacts",           # Контакты (общее)
            "contactsShowPhone",  # Посмотрели телефон
            "contactsMessenger",  # Написали в чат
            "favorites",          # В избранном
            "impressions",        # Показы
            "allSpending",        # Все расходы
            "spending",           # Расходы на объявления
            "presenceSpending",   # Расходы на размещение
            "promoSpending",      # Расходы на целевые действия
            "activeItems"         # Активные объявления
        ]
        
        # Данные запроса
        data = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "grouping": grouping,
            "metrics": metrics,
            "limit": 1000,
            "offset": 0
        }
        
        logger.info(f"Запрос расширенной статистики профиля за период {date_from} - {date_to}, группировка: {grouping}")
        
        # Выполняем запрос
        response = requests.post(stats_url, headers=headers, json=data)
        
        # Проверяем код ответа. Если 429 (Too Many Requests), возвращаем пустой результат
        if response.status_code == 429:
            get_profile_statistics.last_error_code = 429
            logger.warning(f"Превышен лимит запросов к API статистики (429 Too Many Requests)")
            return {}
            
        response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if not response.text.strip():
            logger.warning("Получен пустой ответ от API статистики профиля")
            return {}
        
        # Парсим JSON ответ
        try:
            result = response.json()
            
            # Если группировка по общим значениям, получаем первую группировку
            if grouping == "totals":
                # Получаем метрики из первой группировки
                groupings = result.get('result', {}).get('groupings', [])
                if not groupings:
                    logger.warning("В ответе API отсутствуют группировки")
                    return {}
                
                # Получаем метрики из первой группировки
                metrics_data = groupings[0].get('metrics', [])
                
                # Преобразуем список метрик в словарь {slug: value}
                stats = {metric.get('slug'): metric.get('value', 0) for metric in metrics_data}
                
                # Добавляем расчетные показатели
                calls = stats.get('contactsShowPhone', 0)
                chats = stats.get('contactsMessenger', 0)
                
                # Формируем результат с основными и дополнительными показателями
                result_dict = {
                    "views": stats.get('views', 0),
                    "contacts": stats.get('contacts', 0),
                    "calls": calls,
                    "chats": chats,
                    "favorites": stats.get('favorites', 0),
                    "impressions": stats.get('impressions', 0),
                    
                    # Почему-то для рекламы ('ads') берётся метрика 'spending', которая является суммой всех остальных расходов
                    "spending": {
                        "total": stats.get('spending', 0) + offers_sum,
                        "ads": stats.get('spending', 0),
                        "presence": stats.get('presenceSpending', 0),
                        "promo": stats.get('promoSpending', 0),
                        'sales': offers_sum
                    },
                    "active_items": stats.get('activeItems', 0)
                }
                logger.info(f"Получена статистика: просмотры: {result_dict['views']}, контакты: {result_dict['contacts']}, звонки: {result_dict['calls']}, чаты: {result_dict['chats']}")
                
                # Сохраняем результат в кэш
                get_profile_statistics._stats_cache[cache_key] = (result_dict, current_time)
                
                return result_dict
                
            else:
                # Для других группировок возвращаем полный результат
                return result.get('result', {})
                
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}, содержимое ответа: {response.text[:200]}")
            return {}
            
    except requests.exceptions.RequestException as e:
        # Сохраняем код ошибки, если это 429
        if hasattr(e, 'response') and e.response is not None:
            status_code = e.response.status_code
            if status_code == 429:
                get_profile_statistics.last_error_code = 429
                logger.warning(f"Превышен лимит запросов к API статистики (429 Too Many Requests) в RequestException")
                
        logger.error(f"Ошибка запроса API статистики: {e}")
        return {}
    except Exception as e:
        logger.error(f"Ошибка при получении расширенной статистики профиля: {e}")
        return {}

def get_total_items_count(access_token, status="active"):
    """Получает общее количество объявлений пользователя."""
    try:
        items_url = 'https://api.avito.ru/core/v1/items'
        items_headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        # Запрашиваем первую страницу с минимальным количеством элементов для получения мета-информации
        params = {
            'status': status,
            'per_page': 1,  # Минимальное количество для получения мета-информации
            'page': 1
        }
        
        logger.info(f"Запрос общего количества объявлений со статусом '{status}'")
        
        response = requests.get(items_url, headers=items_headers, params=params)
        response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if not response.text.strip():
            logger.warning("Получен пустой ответ от API объявлений")
            return 0
        
        try:
            result = response.json()
            
            # Получаем мета-информацию о пагинации
            meta = result.get('meta', {})
            per_page = meta.get('per_page', 1)
            current_page = meta.get('page', 1)
            
            # Получаем количество объявлений на текущей странице
            resources = result.get('resources', [])
            items_on_page = len(resources)
            
            # Если на первой странице меньше объявлений чем per_page, значит это все объявления
            if items_on_page < per_page:
                total_items = items_on_page
                logger.info(f"Найдено {total_items} объявлений (все на одной странице)")
                return total_items
            
            # Иначе нужно получить все страницы для точного подсчета
            total_items = 0
            page = 1
            max_pages = 100  # Ограничение для безопасности
            
            while page <= max_pages:
                params['page'] = page
                params['per_page'] = 100  # Увеличиваем размер страницы для эффективности
                
                response = requests.get(items_url, headers=items_headers, params=params)
                response.raise_for_status()
                
                if not response.text.strip():
                    break
                    
                page_result = response.json()
                page_resources = page_result.get('resources', [])
                
                if not page_resources:
                    break
                    
                total_items += len(page_resources)
                
                # Если получили меньше объявлений чем запрашивали, значит это последняя страница
                if len(page_resources) < params['per_page']:
                    break
                    
                page += 1
            
            logger.info(f"Найдено {total_items} объявлений со статусом '{status}' (проверено {page} страниц)")
            return total_items
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}, содержимое ответа: {response.text[:200]}")
            return 0
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к API объявлений: {e}")
        return 0
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении количества объявлений: {e}")
        return 0

def get_cpa_balance(access_token):
    """
    Получает CPA баланс пользователя через API /cpa/v3/balanceInfo
    
    Args:
        access_token: Токен доступа к API
        
    Returns:
        float: CPA баланс в рублях
    """
    try:
        # URL для получения CPA баланса
        cpa_balance_url = 'https://api.avito.ru/cpa/v3/balanceInfo'
        
        # Заголовки запроса
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Пустое тело запроса согласно документации
        data = {}
        
        logger.info("Запрос CPA баланса")
        
        # Выполняем запрос
        response = requests.post(cpa_balance_url, headers=headers, json=data)
        response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if not response.text.strip():
            logger.error("Получен пустой ответ от API CPA баланса")
            return 0
            
        # Парсим JSON ответ
        try:
            balance_data = response.json()
            cpa_balance = balance_data.get('balance', 0)
            
            # Конвертируем из копеек в рубли
            cpa_balance_rub = cpa_balance / 100
            
            logger.info(f"Получен CPA баланс: {cpa_balance_rub} ₽")
            return cpa_balance_rub
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON CPA баланса: {e}, содержимое ответа: {response.text}")
            return 0
            
    except Exception as e:
        logger.error(f"Ошибка при получении CPA баланса: {e}")
        return 0

def get_user_calls(access_token, date_from=None, date_to=None):
    """Получение списка звонков за указанный период (старый API для обратной совместимости)"""
    try:
        if date_from is None or date_to is None:
            current_time = datetime.datetime.now()
            date_from = (current_time - datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            date_to = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        calls_url = 'https://api.avito.ru/calltracking/v1/getCalls/'
        calls_data = {
            'dateTimeFrom': date_from,
            'dateTimeTo': date_to,
            'limit': 100,
            'offset': 0
        }
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        logger.info(f"Запрос звонков с {date_from} по {date_to}")
        
        calls_response = requests.post(calls_url, headers=headers, json=calls_data)
        calls_response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if not calls_response.text.strip():
            logger.warning("Получен пустой ответ от API звонков")
            return {"calls": []}
        
        try:
            calls_result = calls_response.json()
            logger.info(f"Получено {len(calls_result.get('calls', []))} звонков")
            return calls_result
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}, содержимое ответа: {calls_response.text[:200]}")
            return {"calls": []}
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к API звонков: {e}")
        return {"calls": []}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении звонков: {e}")
        return {"calls": []}