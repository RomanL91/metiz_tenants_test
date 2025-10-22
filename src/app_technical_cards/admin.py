import nested_admin

from django.contrib import admin
from django.utils.html import format_html

from app_technical_cards.models import (
    TechnicalCard,
    TechnicalCardVersion,
    TechnicalCardVersionMaterial,
    TechnicalCardVersionWork,
)


class WithNestedIndentMedia:
    class Media:
        css = {
            "all": (
                "admin/css/nested_indent.css",
                "admin/css/entity_highlight.css",
                "admin/css/entity_version_heading.css",
                "admin/css/tc_highlights.css",
            ),
        }


# ---------- NESTED INLINES (материалы и работы внутри версии) ----------


class TCVMaterialNestedInline(WithNestedIndentMedia, nested_admin.NestedTabularInline):
    model = TechnicalCardVersionMaterial
    extra = 0
    ordering = ("order", "id")
    autocomplete_fields = ("material",)
    classes = ["collapse", "entity-mat"]

    fields = (
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

    show_change_link = True

    # ГРУППИРОВКА ПОЛЕЙ + «снапшот процентов»
    fieldsets = (
        (
            "Статус и метаданные",
            {
                "fields": (
                    "is_published",
                    "version_display",
                    "created_at_display",
                ),
                "classes": ["collapse", "entity-meta"],
            },
        ),
        (
            "Процентные настройки (снапшот)",
            {
                "fields": (
                    "materials_markup_percent_display",
                    "works_markup_percent_display",
                    "transport_costs_percent_display",
                    "materials_margin_percent_display",
                    "works_margin_percent_display",
                ),
                "classes": ["collapse", "entity-percents"],
                "description": "Проценты скопированы из TechnicalCard на момент создания версии.",
            },
        ),
        (
            "Себестоимость",
            {
                "fields": (
                    "materials_cost_per_unit_display",
                    "works_cost_per_unit_display",
                    "total_cost_per_unit_display",
                ),
                "classes": ["collapse", "entity-meta"],
            },
        ),
        (
            "Общая стоимость (с надбавками + транспорт)",
            {
                "fields": (
                    "materials_total_cost_per_unit_display",
                    "works_total_cost_per_unit_display",
                    "total_cost_with_markups_per_unit_display",
                ),
                "classes": ["collapse", "entity-meta"],
            },
        ),
        (
            "Цена продажи (с маржинальностью)",
            {
                "fields": (
                    "materials_sale_price_per_unit_display",
                    "works_sale_price_per_unit_display",
                    "total_sale_price_per_unit_display",
                ),
                "classes": ["collapse", "entity-meta"],
            },
        ),
    )

    readonly_fields = (
        "version_display",
        "created_at_display",
        "materials_cost_per_unit_display",
        "works_cost_per_unit_display",
        "total_cost_per_unit_display",
        "materials_total_cost_per_unit_display",
        "works_total_cost_per_unit_display",
        "total_cost_with_markups_per_unit_display",
        "materials_sale_price_per_unit_display",
        "works_sale_price_per_unit_display",
        "total_sale_price_per_unit_display",
        # проценты (снапшот)
        "materials_markup_percent_display",
        "works_markup_percent_display",
        "transport_costs_percent_display",
        "materials_margin_percent_display",
        "works_margin_percent_display",
    )

    def version_display(self, obj):
        return obj.version if obj.pk else "—"

    version_display.short_description = "Версия"

    def created_at_display(self, obj):
        return obj.created_at if obj.pk else "—"

    created_at_display.short_description = "Дата создания"

    # Методы для отображения актуальных расчетных данных
    def materials_cost_per_unit_display(self, obj):

        return self._pill(self._fmt_money(obj.materials_cost_per_unit), "neutral")

    materials_cost_per_unit_display.short_description = (
        "Себестоимость материалов за ед."
    )

    def works_cost_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.works_cost_per_unit), "neutral")

    works_cost_per_unit_display.short_description = "Себестоимость работ за ед."

    def total_cost_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.total_cost_per_unit), "neutral")

    total_cost_per_unit_display.short_description = "Общая себестоимость за ед."

    def materials_total_cost_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.materials_total_cost_per_unit), "info")

    materials_total_cost_per_unit_display.short_description = (
        "Общая стоимость материалов за ед."
    )

    def works_total_cost_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.works_total_cost_per_unit), "info")

    works_total_cost_per_unit_display.short_description = "Общая стоимость работ за ед."

    def total_cost_with_markups_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.total_cost_with_markups_per_unit), "info")

    total_cost_with_markups_per_unit_display.short_description = (
        "Общая стоимость техкарты за ед."
    )

    def materials_sale_price_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.materials_sale_price_per_unit), "success")

    materials_sale_price_per_unit_display.short_description = (
        "Цена продажи материалов за ед."
    )

    def works_sale_price_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.works_sale_price_per_unit), "success")

    works_sale_price_per_unit_display.short_description = "Цена продажи работ за ед."

    def total_sale_price_per_unit_display(self, obj):

        return self._pill(self._fmt_money(obj.total_sale_price_per_unit), "success")

    total_sale_price_per_unit_display.short_description = "Цена продажи техкарты за ед."

    # --- Снапшот процентных настроек версии ---
    def _fmt_percent(self, v):
        return "—" if v in (None, "") else f"{v:.2f} %"

    def materials_markup_percent_display(self, obj):
        return self._pill(
            self._fmt_percent(getattr(obj, "materials_markup_percent", None)), "info"
        )

    materials_markup_percent_display.short_description = "Надбавка на материалы"

    def works_markup_percent_display(self, obj):
        return self._pill(
            self._fmt_percent(getattr(obj, "works_markup_percent", None)), "info"
        )

    works_markup_percent_display.short_description = "Надбавка на работы"

    def transport_costs_percent_display(self, obj):
        return self._pill(
            self._fmt_percent(getattr(obj, "transport_costs_percent", None)), "warning"
        )

    transport_costs_percent_display.short_description = "Транспортные расходы"

    def materials_margin_percent_display(self, obj):
        return self._pill(
            self._fmt_percent(getattr(obj, "materials_margin_percent", None)), "success"
        )

    materials_margin_percent_display.short_description = "Маржинальность материалов"

    def works_margin_percent_display(self, obj):
        return self._pill(
            self._fmt_percent(getattr(obj, "works_margin_percent", None)), "success"
        )

    works_margin_percent_display.short_description = "Маржинальность работ"

    # --- форматирование чисел и «пилюли» ---
    def _fmt_money(self, v):
        return "—" if v in (None, "") else f"{v:.2f}"

    def _fmt_percent(self, v):
        return "—" if v in (None, "") else f"{v:.2f} %"

    def _pill(self, label: str, tone: str = "neutral"):
        # tone: neutral | info | success | warning | danger
        return format_html('<span class="tc-pill tc-{}">{}</span>', tone, label)


# ---------- ОСНОВНЫЕ АДМИНКИ ----------


@admin.register(TechnicalCard)
class TechnicalCardAdmin(WithNestedIndentMedia, nested_admin.NestedModelAdmin):
    list_display = (
        # "id",
        "name",
        "unit_ref",
        "latest_version_display",
        "latest_version_total_sale_price",
        "materials_markup_percent",
        "works_markup_percent",
        "transport_costs_percent",
        "materials_margin_percent",
        "works_margin_percent",
    )
    search_fields = ("name",)
    inlines = [TechnicalCardVersionNestedInline]

    fieldsets = (
        (
            "Основная информация",
            {"fields": ("name", "unit_ref")},
        ),
        (
            "Надбавки и транспортные расходы (%)",
            {
                "fields": (
                    "materials_markup_percent",
                    "works_markup_percent",
                    "transport_costs_percent",
                ),
                "description": "Эти проценты будут скопированы в версию при её создании",
            },
        ),
        (
            "Маржинальность (%)",
            {
                "fields": (
                    "materials_margin_percent",
                    "works_margin_percent",
                ),
                "description": "Эти проценты будут скопированы в версию при её создании",
            },
        ),
    )

    def latest_version_display(self, obj):
        latest = obj.latest_version
        return latest.version if latest else "—"

    latest_version_display.short_description = "Последняя версия"

    def latest_version_total_sale_price(self, obj):
        latest = obj.latest_version
        if not latest:
            return "—"
        v = latest.total_sale_price_per_unit
        return "—" if v in (None, "") else f"{v:.2f}"

    latest_version_total_sale_price.short_description = "Цена продажи за 1 ед. версии"


# @admin.register(TechnicalCardVersion)
class TechnicalCardVersionAdmin(WithNestedIndentMedia, nested_admin.NestedModelAdmin):
    list_display = (
        "id",
        "card",
        "version",
        "total_cost_per_unit",
        "total_cost_with_markups_per_unit",
        "total_sale_price_per_unit",
        "created_at",
        "is_published",
    )
    list_filter = ("is_published", "created_at")
    search_fields = ("card__name", "version")
    autocomplete_fields = ("card",)
    inlines = [TCVMaterialNestedInline, TCVWorkNestedInline]

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": (
                    "card",
                    "is_published",
                    "version_display",
                    "created_at_display",
                )
            },
        ),
        (
            "Проценты (снапшот из TechnicalCard)",
            {
                "fields": (
                    "materials_markup_percent_display",
                    "works_markup_percent_display",
                    "transport_costs_percent_display",
                    "materials_margin_percent_display",
                    "works_margin_percent_display",
                ),
                "classes": ["collapse"],
            },
        ),
        (
            "Себестоимость",
            {
                "fields": (
                    "materials_cost_per_unit",
                    "works_cost_per_unit",
                    "total_cost_per_unit",
                )
            },
        ),
        (
            "Общая стоимость (с надбавками + транспорт)",
            {
                "fields": (
                    "materials_total_cost_per_unit",
                    "works_total_cost_per_unit",
                    "total_cost_with_markups_per_unit",
                )
            },
        ),
        (
            "Цена продажи (с маржинальностью)",
            {
                "fields": (
                    "materials_sale_price_per_unit",
                    "works_sale_price_per_unit",
                    "total_sale_price_per_unit",
                )
            },
        ),
    )

    readonly_fields = (
        "version_display",
        "created_at_display",
        # Проценты readonly т.к. это снапшот
        "materials_markup_percent_display",
        "works_markup_percent_display",
        "transport_costs_percent_display",
        "materials_margin_percent_display",
        "works_margin_percent_display",
        # Все расчетные поля
        "materials_cost_per_unit",
        "works_cost_per_unit",
        "total_cost_per_unit",
        "materials_total_cost_per_unit",
        "works_total_cost_per_unit",
        "total_cost_with_markups_per_unit",
        "materials_sale_price_per_unit",
        "works_sale_price_per_unit",
        "total_sale_price_per_unit",
    )

    def version_display(self, obj):
        return obj.version if obj.pk else "—"

    version_display.short_description = "Версия"

    def created_at_display(self, obj):
        return obj.created_at if obj.pk else "—"

    created_at_display.short_description = "Дата создания"

    def materials_markup_percent_display(self, obj):
        return f"{obj.materials_markup_percent}%" if obj.pk else "—"

    materials_markup_percent_display.short_description = "Надбавка на материалы"

    def works_markup_percent_display(self, obj):
        return f"{obj.works_markup_percent}%" if obj.pk else "—"

    works_markup_percent_display.short_description = "Надбавка на работы"

    def transport_costs_percent_display(self, obj):
        return f"{obj.transport_costs_percent}%" if obj.pk else "—"

    transport_costs_percent_display.short_description = "Транспортные расходы"

    def materials_margin_percent_display(self, obj):
        return f"{obj.materials_margin_percent}%" if obj.pk else "—"

    materials_margin_percent_display.short_description = "Маржинальность материалов"

    def works_margin_percent_display(self, obj):
        return f"{obj.works_margin_percent}%" if obj.pk else "—"

    works_margin_percent_display.short_description = "Маржинальность работ"

    def save_formset(self, request, form, formset, change):
        """Сохраняем строки состава → пересчитаем агрегаты."""
        resp = super().save_formset(request, form, formset, change)
        try:
            form.instance.recalc_totals(save=True)
        except Exception:
            pass
        return resp


# @admin.register(TechnicalCardVersionMaterial)
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
    readonly_fields = ("material_name", "unit_ref", "price_per_unit")


# @admin.register(TechnicalCardVersionWork)
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
    readonly_fields = ("work_name", "unit_ref", "price_per_unit")
