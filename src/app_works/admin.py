from django.contrib import admin
from django.shortcuts import render
from django.urls import path
from django.utils.translation import gettext_lazy as _

from app_works.models import Work


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    change_list_template = "admin/app_works/work/change_list.html"

    list_display = (
        "name",
        "unit_ref",
        "price_per_unit",
        "price_per_labor_hour",
        "calculate_only_by_labor",
        "is_active",
    )
    search_fields = ("name",)
    list_filter = ("unit_ref", "calculate_only_by_labor")

    list_select_related = ("unit_ref",)

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
