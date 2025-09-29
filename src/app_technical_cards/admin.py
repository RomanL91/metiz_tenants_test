from django.contrib import admin

from app_technical_cards.models import (
    TechnicalCard,
    TechnicalCardVersion,
    TechnicalCardVersionMaterial,
    TechnicalCardVersionWork,
)

# ---------- INLINES (состав версии ТК) ----------


class TCVMaterialInline(admin.TabularInline):
    model = TechnicalCardVersionMaterial
    extra = 0
    ordering = ("order", "id")
    raw_id_fields = ("material",)
    fields = (
        "order",
        "material",
        "material_name",
        "unit",
        "qty_per_unit",
        "price_per_unit",
        "line_cost_per_unit_display",
    )
    readonly_fields = ("line_cost_per_unit_display",)

    def line_cost_per_unit_display(self, obj):
        v = obj.line_cost_per_unit
        return "—" if v is None else f"{v:.2f}"

    line_cost_per_unit_display.short_description = "Стоимость на 1 ед (строка)"


class TCVWorkInline(admin.TabularInline):
    model = TechnicalCardVersionWork
    extra = 0
    ordering = ("order", "id")
    raw_id_fields = ("work",)
    fields = (
        "order",
        "work",
        "work_name",
        "unit",
        "qty_per_unit",
        "price_per_unit",
        "line_cost_per_unit_display",
    )
    readonly_fields = ("line_cost_per_unit_display",)

    def line_cost_per_unit_display(self, obj):
        v = obj.line_cost_per_unit
        return "—" if v is None else f"{v:.2f}"

    line_cost_per_unit_display.short_description = "Стоимость на 1 ед (строка)"


# ---------- АДМИНКИ ----------


@admin.register(TechnicalCard)
class TechnicalCardAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "output_unit",
        "code",
        "latest_version_num",
        "latest_version_total_cost",
    )
    search_fields = ("name", "code")

    def latest_version_num(self, obj):
        return obj.latest_version.version if obj.latest_version else "—"

    latest_version_num.short_description = "Последняя версия"

    def latest_version_total_cost(self, obj):
        v = getattr(obj.latest_version, "total_cost_per_unit", None)
        return "—" if v in (None, "") else f"{v:.2f}"

    latest_version_total_cost.short_description = "Цена ТК за 1 ед (посл. версия)"


@admin.register(TechnicalCardVersion)
class TechnicalCardVersionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "card",
        "version",
        "name",
        "output_unit",
        "materials_cost_per_unit",
        "works_cost_per_unit",
        "total_cost_per_unit",
        "created_at",
        "is_published",
    )
    list_filter = ("is_published", "created_at")
    search_fields = ("name", "card__name")
    readonly_fields = (
        "created_at",
        "materials_cost_per_unit",
        "works_cost_per_unit",
        "total_cost_per_unit",
    )
    raw_id_fields = ("card",)
    inlines = (TCVMaterialInline, TCVWorkInline)

    def save_formset(self, request, form, formset, change):
        """Сохраняем строки состава → на всякий случай пересчитаем агрегаты (сигналы уже это делают)."""
        resp = super().save_formset(request, form, formset, change)
        try:
            form.instance.recalc_totals(save=True)
        except Exception:
            pass
        return resp
