from django.contrib import admin
import nested_admin

from app_technical_cards.models import (
    TechnicalCard,
    TechnicalCardVersion,
    TechnicalCardVersionMaterial,
    TechnicalCardVersionWork,
)

# ---------- Миксин для отступов ----------


class WithNestedIndentMedia:
    class Media:
        css = {
            "all": (
                "admin/css/nested_indent.css",
                "admin/css/entity_highlight.css",
                "admin/css/entity_version_heading.css",
            ),
        }


# ---------- NESTED INLINES (материалы и работы внутри версии) ----------


class TCVMaterialNestedInline(WithNestedIndentMedia, nested_admin.NestedTabularInline):
    model = TechnicalCardVersionMaterial
    extra = 0
    ordering = ("order", "id")
    autocomplete_fields = ("material",)
    classes = ["collapse", "entity-mat"]

    # Показываем только нужные поля (снапшоты скрыты через editable=False)
    fields = (
        # "order",
        "material",
        "qty_per_unit",
        "line_cost_per_unit_display",
    )
    readonly_fields = ("line_cost_per_unit_display",)

    def line_cost_per_unit_display(self, obj):
        v = obj.line_cost_per_unit
        return "—" if v is None else f"{v:.2f}"

    line_cost_per_unit_display.short_description = "Стоимость"


class TCVWorkNestedInline(WithNestedIndentMedia, nested_admin.NestedTabularInline):
    model = TechnicalCardVersionWork
    extra = 0
    ordering = ("order", "id")
    autocomplete_fields = ("work",)
    classes = ["collapse", "entity-work"]

    fields = (
        # "order",
        "work",
        "qty_per_unit",
        "line_cost_per_unit_display",
    )
    readonly_fields = ("line_cost_per_unit_display",)

    def line_cost_per_unit_display(self, obj):
        v = obj.line_cost_per_unit
        return "—" if v is None else f"{v:.2f}"

    line_cost_per_unit_display.short_description = "Стоимость"


# ---------- NESTED INLINE (версии внутри карточки) ----------


class TechnicalCardVersionNestedInline(
    WithNestedIndentMedia, nested_admin.NestedStackedInline
):
    model = TechnicalCardVersion
    extra = 0
    inlines = [TCVMaterialNestedInline, TCVWorkNestedInline]
    classes = ["collapse", "entity-version"]

    fields = (
        "is_published",
        "version",
        "created_at",
        "materials_cost_per_unit",
        "works_cost_per_unit",
        "total_cost_per_unit",
    )
    readonly_fields = (
        "version",  # Генерируется автоматически
        "created_at",
        "materials_cost_per_unit",
        "works_cost_per_unit",
        "total_cost_per_unit",
    )


# ---------- ОСНОВНЫЕ АДМИНКИ ----------


@admin.register(TechnicalCard)
class TechnicalCardAdmin(WithNestedIndentMedia, nested_admin.NestedModelAdmin):
    list_display = (
        "id",
        "name",
        "output_unit",
        "latest_version_display",
        "latest_version_total_cost",
    )
    search_fields = ("name",)
    inlines = [TechnicalCardVersionNestedInline]

    def latest_version_display(self, obj):
        latest = obj.latest_version
        return latest.version if latest else "—"

    latest_version_display.short_description = "Последняя версия"

    def latest_version_total_cost(self, obj):
        latest = obj.latest_version
        if not latest:
            return "—"
        v = latest.total_cost_per_unit
        return "—" if v in (None, "") else f"{v:.2f}"

    latest_version_total_cost.short_description = "Цена за 1 ед."


@admin.register(TechnicalCardVersion)
class TechnicalCardVersionAdmin(WithNestedIndentMedia, nested_admin.NestedModelAdmin):
    list_display = (
        "id",
        "card",
        "version",
        "materials_cost_per_unit",
        "works_cost_per_unit",
        "total_cost_per_unit",
        "created_at",
        "is_published",
    )
    list_filter = ("is_published", "created_at")
    search_fields = ("card__name", "version")
    readonly_fields = (
        "version",  # Генерируется автоматически
        "created_at",
        "materials_cost_per_unit",
        "works_cost_per_unit",
        "total_cost_per_unit",
    )
    autocomplete_fields = ("card",)
    inlines = [TCVMaterialNestedInline, TCVWorkNestedInline]

    def save_formset(self, request, form, formset, change):
        """Сохраняем строки состава → пересчитаем агрегаты."""
        resp = super().save_formset(request, form, formset, change)
        try:
            form.instance.recalc_totals(save=True)
        except Exception:
            pass
        return resp


@admin.register(TechnicalCardVersionMaterial)
class TechnicalCardVersionMaterialAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "technical_card_version",
        "material",
        "material_name",
        "qty_per_unit",
        "price_per_unit",
    )
    search_fields = ("material_name", "material__name")
    autocomplete_fields = ("material", "technical_card_version")
    readonly_fields = ("material_name", "unit", "price_per_unit")


@admin.register(TechnicalCardVersionWork)
class TechnicalCardVersionWorkAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "technical_card_version",
        "work",
        "work_name",
        "qty_per_unit",
        "price_per_unit",
    )
    search_fields = ("work_name", "work__name")
    autocomplete_fields = ("work", "technical_card_version")
    readonly_fields = ("work_name", "unit", "price_per_unit")
