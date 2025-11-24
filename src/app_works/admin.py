from datetime import datetime
from io import BytesIO

from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path
from django.utils.translation import gettext_lazy as _
from openpyxl import Workbook

from app_works.models import Work


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    change_list_template = "admin/app_works/work/change_list.html"

    list_display = (
        "name",
        "unit_ref",
        "supplier_ref",
        "price_per_unit",
        "price_per_labor_hour",
        "labor_hours",
        "calculate_only_by_labor",
        "is_active",
    )
    search_fields = ("name",)
    list_filter = ("unit_ref", "calculate_only_by_labor")

    autocomplete_fields = ("supplier_ref",)
    list_select_related = ("unit_ref", "supplier_ref")
    actions = ("export_works_to_excel",)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import/",
                self.admin_site.admin_view(self.import_works_view),
                name="app_works_work_import",
            ),
        ]
        return custom_urls + urls

    def import_works_view(self, request):
        context = {
            **self.admin_site.each_context(request),
            "title": _("Импорт работ"),
        }
        return render(request, "admin/app_works/work/import.html", context)
    
    @admin.action(description=_("Экспорт в Excel"))
    def export_works_to_excel(self, request, queryset):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = str(_("Работы"))

        headers = (
            _("Наименование"),
            _("Единица измерения"),
            _("Цена"),
            _("Предварительная расценка за человеко-час"),
            _("Кол-во человеко-часов"),
            _("Поставщик"),
            _("Считать только по ЧЧ"),
        )
        worksheet.append([str(header) for header in headers])

        queryset = queryset.select_related("unit_ref", "supplier_ref")

        for work in queryset:
            worksheet.append(
                (
                    work.name,
                    str(work.unit_ref) if work.unit_ref else "",
                    work.price_per_unit,
                    work.price_per_labor_hour if work.price_per_labor_hour is not None else "",
                    work.labor_hours,
                    work.supplier_ref.name if work.supplier_ref else "",
                    "Да" if work.calculate_only_by_labor else "Нет",
                )
            )

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"works_{timestamp}.xlsx"

        response = HttpResponse(
            output.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

