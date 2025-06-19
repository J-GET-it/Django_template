#!/usr/bin/env python
import os
import sys
import django
from django.conf import settings

# Добавляем корневую папку проекта в PYTHONPATH
sys.path.append('/Users/ramilnurgaleev/Dev/Django_template')

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_app.settings')
django.setup()

from bot.models import AvitoAccount
from bot.services import get_weekly_statistics

def test_multiple_accounts():
    """Тест для проверки, что разные аккаунты получают разные данные"""
    
    # Получаем все аккаунты Авито
    accounts = AvitoAccount.objects.filter(
        client_id__isnull=False, 
        client_secret__isnull=False
    ).exclude(client_id="none")
    
    print(f"Найдено {accounts.count()} аккаунтов для тестирования")
    
    results = {}
    
    for account in accounts:
        print(f"\nТестируем аккаунт: {account.name} (ID: {account.id})")
        print(f"Client ID: {account.client_id}")
        
        try:
            # Получаем недельную статистику
            stats = get_weekly_statistics(account.client_id, account.client_secret)
            
            # Сохраняем результат
            results[account.id] = {
                'name': account.name,
                'calls_total': stats['calls']['total'],
                'balance_real': stats['balance_real'],
                'items_total': stats['items']['total'],
                'views': stats['statistics']['views']
            }
            
            print(f"  Звонки: {stats['calls']['total']}")
            print(f"  Баланс: {stats['balance_real']} ₽")
            print(f"  Объявления: {stats['items']['total']}")
            print(f"  Просмотры: {stats['statistics']['views']}")
            
        except Exception as e:
            print(f"  Ошибка: {e}")
    
    # Проверяем, отличаются ли результаты
    print("\n" + "="*50)
    print("АНАЛИЗ РЕЗУЛЬТАТОВ:")
    print("="*50)
    
    if len(results) < 2:
        print("Недостаточно аккаунтов для сравнения")
        return
    
    # Сравниваем результаты
    account_ids = list(results.keys())
    first_account = results[account_ids[0]]
    
    all_same = True
    for i in range(1, len(account_ids)):
        current_account = results[account_ids[i]]
        
        if (first_account['calls_total'] != current_account['calls_total'] or
            first_account['balance_real'] != current_account['balance_real'] or
            first_account['items_total'] != current_account['items_total'] or
            first_account['views'] != current_account['views']):
            all_same = False
            break
    
    if all_same:
        print("⚠️  ПРОБЛЕМА: Все аккаунты возвращают одинаковые данные!")
        print("Это указывает на проблему с кэшированием.")
    else:
        print("✅ УСПЕХ: Аккаунты возвращают разные данные!")
        print("Проблема с кэшированием решена.")
    
    # Детальное сравнение
    print("\nДетальное сравнение:")
    for account_id, data in results.items():
        print(f"{data['name']}: звонки={data['calls_total']}, баланс={data['balance_real']}, объявления={data['items_total']}, просмотры={data['views']}")

if __name__ == "__main__":
    test_multiple_accounts() 