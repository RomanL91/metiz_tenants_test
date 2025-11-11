from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path
from django.utils.translation import gettext_lazy as _
from openpyxl import Workbook

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
    actions = ("export_materials_to_excel",)

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

    @admin.action(description=_("Экспорт в Excel"))
    def export_materials_to_excel(self, request, queryset):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = str(_("Материалы"))

        headers = (
            _("Наименование"),
            _("Единица измерения"),
            _("Цена"),
            _("Поставщик"),
            _("НДС %"),
        )
        worksheet.append([str(header) for header in headers])

        queryset = queryset.select_related("unit_ref", "supplier_ref")

        for material in queryset:
            worksheet.append(
                (
                    material.name,
                    str(material.unit_ref) if material.unit_ref else "",
                    material.price_per_unit,
                    material.supplier_ref.name if material.supplier_ref else "",
                    material.vat_percent if material.vat_percent is not None else "",
                )
            )

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"materials_{timestamp}.xlsx"

        response = HttpResponse(
            output.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response