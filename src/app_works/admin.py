from django.contrib import admin

from app_works.models import Work


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    list_display_links = ("id", "name")
    search_fields = ("name",)
    ordering = ("name", "id")
