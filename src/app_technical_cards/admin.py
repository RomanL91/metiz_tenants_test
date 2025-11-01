import json
import logging
import nested_admin

from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _

from app_technical_cards.models import (
    TechnicalCard,
    TechnicalCardVersion,
    TechnicalCardVersionMaterial,
    TechnicalCardVersionWork,
)

from .services_versioning import (
    create_version_from_payload,
    create_version_from_latest,
)

log = logging.getLogger("app_technical_cards.admin")


class OnlySaveMediaMixin:
    class Media:
        css = {"all": ("admin/css/only_save.css",)}


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
    fields = ("work", "qty_per_unit", "line_cost_per_unit_display")
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
        "materials_markup_percent_display",
        "works_markup_percent_display",
        "transport_costs_percent_display",
        "materials_margin_percent_display",
        "works_margin_percent_display",
    )

    # — Метаданные
    def version_display(self, obj):
        return obj.version if obj.pk else "—"

    version_display.short_description = "Версия"

    def created_at_display(self, obj):
        return obj.created_at if obj.pk else "—"

    created_at_display.short_description = "Дата создания"

    # — Деньги
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

    # — Проценты
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

    # — Утилиты
    def _fmt_money(self, v):
        return "—" if v in (None, "") else f"{v:.2f}"

    def _fmt_percent(self, v):
        return "—" if v in (None, "") else f"{v:.2f} %"

    def _pill(self, label: str, tone: str = "neutral"):
        return format_html('<span class="tc-pill tc-{}">{}</span>', tone, label)


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
    inlines = [TechnicalCardVersionNestedInline]

    fieldsets = (
        ("Основная информация", {"fields": ("name", "unit_ref")}),
        (
            "Надбавки и транспортные расходы (%)",
            {
                "fields": (
                    (
                        "materials_markup_percent",
                        "works_markup_percent",
                        "transport_costs_percent",
                    ),
                ),
                "description": "Эти проценты будут скопированы в версию при её создании",
            },
        ),
        (
            "Маржинальность (%)",
            {
                "fields": (("materials_margin_percent", "works_margin_percent"),),
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

    VERSION_TRIGGER_FIELDS = {
        "materials_markup_percent",
        "works_markup_percent",
        "transport_costs_percent",
        "materials_margin_percent",
        "works_margin_percent",
    }

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        print("[TC][admin.save_model] change=", change, " obj_id=", obj.id)
        log.debug(
            "admin.save_model change=%s obj_id=%s", change, getattr(obj, "id", None)
        )

        if not change:
            payload_raw = request.POST.get("_tc_initial_composition") or ""
            print(
                "[TC][admin.save_model] _tc_initial_composition length=",
                len(payload_raw),
            )
            if payload_raw.strip():
                try:
                    payload = json.loads(payload_raw)
                    mats = payload.get("materials") or []
                    works = payload.get("works") or []
                    print(
                        "[TC][admin.save_model] parsed composition: mats=",
                        len(mats),
                        " works=",
                        len(works),
                    )
                except Exception as e:
                    self.message_user(
                        request,
                        f"DEBUG: не удалось разобрать стартовый состав ({e})",
                        level=messages.WARNING,
                    )
                    print("[TC][admin.save_model] JSON parse error:", e)
                    return
                ver = create_version_from_payload(
                    card=obj, materials=mats, works=works, publish=False
                )
                self.message_user(
                    request,
                    f"DEBUG: создана версия v{ver.version} из стартового состава.",
                )
                print(
                    "[TC][admin.save_model] created version id=",
                    ver.id,
                    " version=",
                    ver.version,
                )
            else:
                self.message_user(
                    request,
                    "DEBUG: _tc_initial_composition пуст — версия при создании не создана.",
                    level=messages.WARNING,
                )
            return

        # Если фронт заранее создал версию — выходим
        if request.POST.get("_tc_version_created_by_js"):
            self.message_user(
                request,
                "DEBUG: фронт уже создал новую версию (флаг _tc_version_created_by_js).",
            )
            print(
                "[TC][admin.save_model] skip — flag _tc_version_created_by_js present"
            )
            return

        # Fallback: если фронт не вызвал API, но в скрытом поле есть состав — создаём версию из него
        hidden_raw = request.POST.get("_tc_initial_composition") or ""
        if hidden_raw.strip():
            try:
                payload = json.loads(hidden_raw)
                mats = payload.get("materials") or []
                works = payload.get("works") or []
                if mats or works:
                    ver = create_version_from_payload(
                        card=obj, materials=mats, works=works, publish=False
                    )
                    self.message_user(
                        request,
                        f"DEBUG: создана версия v{ver.version} (fallback из скрытого поля).",
                    )
                    print(
                        "[TC][admin.save_model] Fallback created version id=",
                        ver.id,
                        " version=",
                        ver.version,
                    )
                    return
            except Exception as e:
                self.message_user(
                    request,
                    f"DEBUG: fallback не сработал — плохой JSON ({e})",
                    level=messages.WARNING,
                )
                print("[TC][admin.save_model] Fallback JSON parse error:", e)

        # Если проценты менялись — клонируем latest в новую версию
        changed = set(getattr(form, "changed_data", []) or [])
        print("[TC][admin.save_model] changed_fields=", changed)
        if changed & self.VERSION_TRIGGER_FIELDS:
            ver = create_version_from_latest(card=obj, publish=False)
            self.message_user(
                request,
                f"DEBUG: проценты изменены — создана новая версия v{ver.version}.",
            )
            print(
                "[TC][admin.save_model] created (from latest) version id=",
                ver.id,
                " version=",
                ver.version,
            )


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
        "materials_markup_percent_display",
        "works_markup_percent_display",
        "transport_costs_percent_display",
        "materials_margin_percent_display",
        "works_margin_percent_display",
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
        return f"{obj.materials_markup_percent:.2f}%" if obj.pk else "—"

    materials_markup_percent_display.short_description = "Надбавка на материалы"

    def works_markup_percent_display(self, obj):
        return f"{obj.works_markup_percent:.2f}%" if obj.pk else "—"

    works_markup_percent_display.short_description = "Надбавка на работы"

    def transport_costs_percent_display(self, obj):
        return f"{obj.transport_costs_percent:.2f}%" if obj.pk else "—"

    transport_costs_percent_display.short_description = "Транспортные расходы"

    def materials_margin_percent_display(self, obj):
        return f"{obj.materials_margin_percent:.2f}%" if obj.pk else "—"

    materials_margin_percent_display.short_description = "Маржинальность материалов"

    def works_margin_percent_display(self, obj):
        return f"{obj.works_margin_percent:.2f}%" if obj.pk else "—"

    works_margin_percent_display.short_description = "Маржинальность работ"

    def save_formset(self, request, form, formset, change):
        resp = super().save_formset(request, form, formset, change)
        try:
            form.instance.recalc_totals(save=True)
        except Exception:
            pass
        return resp


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
