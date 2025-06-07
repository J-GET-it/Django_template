from django.contrib import admin
from .models import User, AvitoAccount, UserAvitoAccount, AvitoAccountDailyStats, AvitoAccountWeeklyStats

class UserAdmin(admin.ModelAdmin):
    list_display = ('user_name',)  # Удалены недопустимые поля
    search_fields = ('user_name',)
    ordering = ('-telegram_id',)  # Изменено на существующее поле

    def get_queryset(self, request):
        """Переопределяем метод для обработки ошибок при получении пользователей."""
        try:
            return super().get_queryset(request)
        except Exception as e:
            return User.objects.none()

class AvitoAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'client_id', 'last_balance', 'daily_expense', 'weekly_expense')
    search_fields = ('name',)
    list_filter = ('name',)

class UserAvitoAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'avito_account')
    search_fields = ('user__user_name', 'avito_account__name')
    list_filter = ('avito_account',)

class AvitoAccountDailyStatsAdmin(admin.ModelAdmin):
    list_display = ('avito_account', 'date', 'total_calls', 'total_chats', 'views', 'contacts', 'daily_expense')
    list_filter = ('avito_account', 'date')
    search_fields = ('avito_account__name',)
    date_hierarchy = 'date'
    ordering = ('-date',)

class AvitoAccountWeeklyStatsAdmin(admin.ModelAdmin):
    list_display = ('avito_account', 'period', 'week_start_date', 'week_end_date', 'total_calls', 'views', 'contacts', 'weekly_expense')
    list_filter = ('avito_account', 'week_start_date')
    search_fields = ('avito_account__name', 'period')
    date_hierarchy = 'week_start_date'
    ordering = ('-week_start_date',)
    readonly_fields = ('created_at',)
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('avito_account', 'period', 'week_start_date', 'week_end_date')
        }),
        ('Звонки и сообщения', {
            'fields': ('total_calls', 'answered_calls', 'missed_calls', 'total_chats', 'new_chats', 'phones_received')
        }),
        ('Рейтинг и отзывы', {
            'fields': ('rating', 'total_reviews', 'weekly_reviews')
        }),
        ('Объявления', {
            'fields': ('total_items', 'xl_promotion_count')
        }),
        ('Статистика', {
            'fields': ('views', 'contacts', 'favorites')
        }),
        ('Финансы', {
            'fields': ('balance_real', 'balance_bonus', 'advance', 'cpa_balance', 'weekly_expense')
        }),
        ('Дополнительно', {
            'fields': ('expenses_details', 'created_at'),
            'classes': ('collapse',)
        })
    )

admin.site.register(User, UserAdmin)
admin.site.register(AvitoAccount, AvitoAccountAdmin)
admin.site.register(UserAvitoAccount, UserAvitoAccountAdmin)
admin.site.register(AvitoAccountDailyStats, AvitoAccountDailyStatsAdmin)
admin.site.register(AvitoAccountWeeklyStats, AvitoAccountWeeklyStatsAdmin)
