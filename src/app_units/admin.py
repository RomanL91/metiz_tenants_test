from django.contrib import admin

from app_units.models import Unit


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("symbol", "name", "is_active")
    search_fields = ("symbol", "name")
    list_filter = ("is_active",)
