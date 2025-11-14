import nested_admin
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from app_technical_cards.models import (TechnicalCard, TechnicalCardVersion,
                                        TechnicalCardVersionMaterial,
                                        TechnicalCardVersionWork)

from .services_versioning import handle_tc_save


class OnlySaveMediaMixin:
    class Media:
        css = {"all": ("app_technical_cards/admin/css/only_save.css",)}


class WithNestedIndentMedia:
    class Media:
        css = {
            "all": (
                "app_technical_cards/admin/css/nested_indent.css",
                "app_technical_cards/admin/css/entity_highlight.css",
                "app_technical_cards/admin/css/entity_version_heading.css",
                "app_technical_cards/admin/css/tc_highlights.css",
                "app_technical_cards/admin/css/autocomplete.css",
            ),
        }


class SaveKeepsEditingMixin(admin.ModelAdmin):
    def _continue_url(self, request, obj):
        opts = self.model._meta
        return reverse(
            f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk]
        )

    def response_post_save_add(self, request, obj):
        if "_popup" in request.POST:
            return super().response_post_save_add(request, obj)
        self.message_user(request, _("Сохранено. Продолжаем редактирование."))
        return HttpResponseRedirect(self._continue_url(request, obj))

    def response_post_save_change(self, request, obj):
        if "_popup" in request.POST:
            return super().response_post_save_change(request, obj)
        self.message_user(request, _("Сохранено. Продолжаем редактирование."))
        return HttpResponseRedirect(self._continue_url(request, obj))


class TCVMaterialNestedInline(WithNestedIndentMedia, nested_admin.NestedTabularInline):
    model = TechnicalCardVersionMaterial
    extra = 0
    ordering = ("order", "id")
    autocomplete_fields = ("material",)
    classes = ["collapse", "entity-mat"]
    fields = ("material", "qty_per_unit", "line_cost_per_unit_display")
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
        "calculation_method",
        "qty_per_unit",
        "line_cost_per_unit_display",
    )
    readonly_fields = ("line_cost_per_unit_display",)

    def line_cost_per_unit_display(self, obj):
        v = obj.line_cost_per_unit
        return "—" if v is None else f"{v:.2f}"

    line_cost_per_unit_display.short_description = "Стоимость"


class TechnicalCardVersionNestedInline(
    WithNestedIndentMedia, nested_admin.NestedStackedInline
):
    model = TechnicalCardVersion
    extra = 0
    inlines = [TCVMaterialNestedInline, TCVWorkNestedInline]
    classes = ["collapse", "entity-version"]
    show_change_link = True

    fieldsets = (
        (
            "Статус и метаданные",
            {
                "fields": ("is_published", "version_display", "created_at_display"),
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

    def _fmt_money(self, v):
        return "—" if v in (None, "") else f"{v:.2f}"

    def _pill(self, label, tone="neutral"):
        return format_html('<span class="tc-pill tc-{}">{}</span>', tone, label)

    def materials_cost_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.materials_cost_per_unit), "neutral")

    def works_cost_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.works_cost_per_unit), "neutral")

    def total_cost_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.total_cost_per_unit), "neutral")

    def materials_total_cost_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.materials_total_cost_per_unit), "info")

    def works_total_cost_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.works_total_cost_per_unit), "info")

    def total_cost_with_markups_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.total_cost_with_markups_per_unit), "info")

    def materials_sale_price_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.materials_sale_price_per_unit), "success")

    def works_sale_price_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.works_sale_price_per_unit), "success")

    def total_sale_price_per_unit_display(self, obj):
        return self._pill(self._fmt_money(obj.total_sale_price_per_unit), "success")

    def _fmt_percent(self, v):
        return "—" if v in (None, "") else f"{v:.2f} %"

    def materials_markup_percent_display(self, obj):
        return self._fmt_percent(obj.materials_markup_percent)

    materials_markup_percent_display.short_description = "Надбавка на материалы"

    def works_markup_percent_display(self, obj):
        return self._fmt_percent(obj.works_markup_percent)

    works_markup_percent_display.short_description = "Надбавка на работы"

    def transport_costs_percent_display(self, obj):
        return self._fmt_percent(obj.transport_costs_percent)

    transport_costs_percent_display.short_description = "Транспортные расходы"

    def materials_margin_percent_display(self, obj):
        return self._fmt_percent(obj.materials_margin_percent)

    materials_margin_percent_display.short_description = "Маржинальность материалов"

    def works_margin_percent_display(self, obj):
        return self._fmt_percent(obj.works_margin_percent)

    works_margin_percent_display.short_description = "Маржинальность работ"


@admin.register(TechnicalCard)
class TechnicalCardAdmin(
    SaveKeepsEditingMixin,
    OnlySaveMediaMixin,
    WithNestedIndentMedia,
    nested_admin.NestedModelAdmin,
):
    change_form_template = "admin/app_technical_cards/technicalcard/change_form.html"

    list_display = (
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
    save_on_top = True
    inlines = [TechnicalCardVersionNestedInline]

    fieldsets = (
        (_("Основная информация"), {"fields": ("name", "unit_ref")}),
        (
            _("Надбавки и транспорт (%)"),
            {
                "fields": (
                    (
                        "materials_markup_percent",
                        "works_markup_percent",
                        "transport_costs_percent",
                    ),
                ),
                "classes": ["tc-hide-percents"],
            },
        ),
        (
            _("Маржинальность (%)"),
            {
                "fields": (("materials_margin_percent", "works_margin_percent"),),
                "classes": ["tc-hide-percents"],
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

    latest_version_total_sale_price.short_description = "Цена продажи (за 1 ед.)"

    def save_model(self, request, obj, form, change):

        changed = set(getattr(form, "changed_data", []) or [])

        if change and obj.pk:
            try:
                old_obj = TechnicalCard.objects.get(pk=obj.pk)
                percent_fields = [
                    "materials_markup_percent",
                    "works_markup_percent",
                    "transport_costs_percent",
                    "materials_margin_percent",
                    "works_margin_percent",
                ]
                for field_name in percent_fields:
                    old_val = getattr(old_obj, field_name)
                    new_val = getattr(obj, field_name)
                    print(f"{field_name}: {old_val} -> {new_val}")
                    if old_val != new_val:
                        changed.add(field_name)
                        print(f"  ^^^ CHANGED!")
            except TechnicalCard.DoesNotExist:
                pass

        super().save_model(request, obj, form, change)

        created = handle_tc_save(obj, request, change=change, changed_fields=changed)

        if created:
            self.message_user(
                request,
                f"✅ Создана новая версия v{created.version}",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "⚠️ Версия НЕ создана",
                level=messages.WARNING,
            )
        print("=" * 80)


# @admin.register(TechnicalCardVersion)
class TechnicalCardVersionAdmin(
    SaveKeepsEditingMixin, WithNestedIndentMedia, nested_admin.NestedModelAdmin
):
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
    readonly_fields = (
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
