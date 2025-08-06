from django.db import models
import datetime
import json


class User(models.Model):
    telegram_id = models.CharField(
        primary_key=True,
        max_length=50
    )
    user_name = models.CharField(
        max_length=35,
        verbose_name='Имя',
    )
    
    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return self.user_name


class AvitoAccount(models.Model):
    name = models.CharField(
        max_length=100,
        verbose_name='Имя аккаунта',
    )
    client_id = models.CharField(
        max_length=50,
        verbose_name='Client ID Авито',
        null=True,
        blank=True,
        default="none",
    )
    client_secret = models.CharField(
        max_length=100,
        verbose_name='Client Secret Авито',
        null=True,
        blank=True,
        default="none",
    )
    daily_report_tg_id = models.CharField(
        max_length=50,
        verbose_name='Telegram ID для дневных отчетов',
        null=True,
        blank=True,
    )
    weekly_report_tg_id = models.CharField(
        max_length=50,
        verbose_name='Telegram ID для недельных отчетов',
        null=True,
        blank=True,
    )
    # Добавляем поля для отслеживания расходов
    daily_expense = models.FloatField(
        verbose_name='Дневной расход',
        default=0,
    )
    weekly_expense = models.FloatField(
        verbose_name='Недельный расход',
        default=0,
    )
    last_balance = models.FloatField(
        verbose_name='Последний баланс',
        default=0,
    )
    last_balance_check = models.DateTimeField(
        verbose_name='Время последней проверки баланса',
        null=True,
        blank=True,
    )
    
    class Meta:
        verbose_name = 'Аккаунт Авито'
        verbose_name_plural = 'Аккаунты Авито'
    
    def __str__(self):
        return self.name
    
    
class UserAvitoAccount(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='avito_accounts',
        verbose_name='Пользователь'
    )
    avito_account = models.ForeignKey(
        AvitoAccount,
        on_delete=models.CASCADE,
        related_name='users',
        verbose_name='Аккаунт Авито'
    )
    
    class Meta:
        verbose_name = 'Связь пользователь-аккаунт'
        verbose_name_plural = 'Связи пользователей и аккаунтов'
        unique_together = ('user', 'avito_account')
        
    def __str__(self):
        return f"{self.user.user_name} - {self.avito_account.name}"


class AvitoAccountDailyStats(models.Model):
    """Модель для хранения ежедневной статистики аккаунта Авито"""
    avito_account = models.ForeignKey(
        AvitoAccount,
        on_delete=models.CASCADE,
        related_name='daily_stats',
        verbose_name='Аккаунт Авито'
    )
    date = models.DateField(
        verbose_name='Дата статистики'
    )
    
    # Основные показатели
    total_calls = models.IntegerField(
        verbose_name='Всего звонков',
        default=0
    )
    answered_calls = models.IntegerField(
        verbose_name='Отвеченные звонки',
        default=0
    )
    missed_calls = models.IntegerField(
        verbose_name='Пропущенные звонки',
        default=0
    )
    
    total_chats = models.IntegerField(
        verbose_name='Всего чатов',
        default=0
    )
    new_chats = models.IntegerField(
        verbose_name='Новые чаты',
        default=0
    )
    
    phones_received = models.IntegerField(
        verbose_name='Показы телефона',
        default=0
    )
    
    # Рейтинг и отзывы
    rating = models.FloatField(
        verbose_name='Рейтинг',
        default=0
    )
    total_reviews = models.IntegerField(
        verbose_name='Всего отзывов',
        default=0
    )
    daily_reviews = models.IntegerField(
        verbose_name='Отзывы за день',
        default=0
    )
    
    # Объявления
    total_items = models.IntegerField(
        verbose_name='Всего объявлений',
        default=0
    )
    xl_promotion_count = models.IntegerField(
        verbose_name='Объявления с XL продвижением',
        default=0
    )
    
    # Статистика просмотров и контактов
    views = models.IntegerField(
        verbose_name='Просмотры',
        default=0
    )
    contacts = models.IntegerField(
        verbose_name='Контакты',
        default=0
    )
    favorites = models.IntegerField(
        verbose_name='В избранном',
        default=0
    )    
    impressions = models.IntegerField(
        verbose_name='Показы',
        default=0
    )
    impressionsToViewsConversion = models.IntegerField(
        verbose_name='Конверсия показов в просмотры',
        default=0
    )
    
    # Финансы
    balance_real = models.FloatField(
        verbose_name='Реальный баланс',
        default=0
    )
    balance_bonus = models.FloatField(
        verbose_name='Бонусы',
        default=0
    )
    advance = models.FloatField(
        verbose_name='Аванс',
        default=0
    )
    daily_expense = models.FloatField(
        verbose_name='Расход за день',
        default=0
    )
    
    class Meta:
        verbose_name = 'Ежедневная статистика аккаунта'
        verbose_name_plural = 'Ежедневная статистика аккаунтов'
        # Уникальное ограничение по аккаунту и дате
        unique_together = ('avito_account', 'date')
        # Сортировка по убыванию даты
        ordering = ['-date']
        
    def __str__(self):
        return f"Статистика {self.avito_account.name} за {self.date}"


class Settings(models.Model):
    """Модель для хранения настроек приложения"""
    key = models.CharField(
        max_length=100,
        verbose_name='Ключ настройки',
        unique=True
    )
    value = models.TextField(
        verbose_name='Значение настройки'
    )
    description = models.CharField(
        max_length=255,
        verbose_name='Описание настройки',
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    class Meta:
        verbose_name = 'Настройка'
        verbose_name_plural = 'Настройки'
        
    def __str__(self):
        return f"{self.key}: {self.value}"
    
    @classmethod
    def get_value(cls, key, default=None):
        """Получить значение настройки по ключу"""
        try:
            setting = cls.objects.get(key=key)
            return setting.value
        except cls.DoesNotExist:
            return default
    
    @classmethod
    def set_value(cls, key, value, description=None):
        """Установить значение настройки"""
        setting, created = cls.objects.update_or_create(
            key=key,
            defaults={
                'value': value,
                'description': description
            }
        )
        return setting