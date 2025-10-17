from django.contrib import admin

from app_materials.models import Material


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "unit",
        "price_per_unit",
        "is_active",
    )
    search_fields = ("name",)
    list_filter = ("unit",)
