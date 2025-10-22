from decimal import Decimal
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from app_materials.models import Material


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "unit_ref",
        "price_per_unit",  # без НДС
        "price_with_vat_display",  # ← NEW: с НДС
        "supplier_ref",
        "vat_percent",
        "is_active",
    )
    search_fields = ("name",)
    list_filter = ("unit_ref",)
    autocomplete_fields = ("supplier_ref",)
    list_select_related = ("supplier_ref",)
    save_on_top = True

    @admin.display(description=_("Цена с НДС"))
    def price_with_vat_display(self, obj: Material) -> Decimal:
        return obj.price_with_vat()
