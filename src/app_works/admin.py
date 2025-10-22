from django.contrib import admin

from app_works.models import Work


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "unit_ref",
        "price_per_unit",
        "is_active",
    )
    search_fields = ("name",)
    list_filter = ("unit_ref",)
