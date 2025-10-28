from decimal import Decimal

from django.urls import path
from django.contrib import admin
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from app_materials.models import Material


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    change_list_template = "admin/app_materials/material/change_list.html"

    list_display = (
        "name",
        "unit_ref",
        "price_per_unit",
        "price_with_vat_display",
        "supplier_ref",
        "vat_percent",
        "is_active",
    )
    search_fields = ("name",)
    list_filter = ("unit_ref",)
    autocomplete_fields = ("supplier_ref",)
    list_select_related = ("supplier_ref",)
    save_on_top = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import/",
                self.admin_site.admin_view(self.import_materials_view),
                name="app_materials_material_import",
            ),
        ]
        return custom_urls + urls

    def import_materials_view(self, request):
        context = {
            **self.admin_site.each_context(request),
            "title": _("Импорт материалов"),
        }
        return render(request, "admin/app_materials/material/import.html", context)

    @admin.display(description=_("Цена с НДС"))
    def price_with_vat_display(self, obj: Material) -> Decimal:
        return obj.price_with_vat()
