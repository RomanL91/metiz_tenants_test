"""Админ-панель для модуля «Сметы» (app_outlay).

Назначение файла
----------------
Этот модуль настраивает интерфейс Django Admin для работы со «Сметами»:
- Регистрация и настройка ModelAdmin'ов: `EstimateAdmin`, `GroupAdmin`.
- Inline-редактирование связей «Группа ↔ Версия ТК» через
  `GroupTechnicalCardLinkInline` с удобными вычисляемыми полями.
- Кастомные admin-эндпоинты:
    * `api_calc` — расчёт показателей по версии ТК и количеству;
    * `tc_autocomplete` — простой автокомплит/батч-сопоставление ТК (POST JSON);
    * `api_auto_match` — батч-автоматическое сопоставление ТК (POST JSON).
- Сервисные функции разбора Excel-листа с кешированием:
    * `_load_full_sheet_rows()` — чтение полного листа (openpyxl, read_only).
    * `_load_full_sheet_rows_cached()` — та же выборка с кешем (django-redis).
- Построение «чернового превью» по импортированному файлу:
    * разбор ролей колонок (NAME_OF_WORK/UNIT/QTY/…);
    * нормализация единиц измерения;
    * извлечение кандидатов ТК и раскладка по иерархии групп из аннотации.

Важно
-----
- Все строки интерфейса обёрнуты в `gettext_lazy(_)` и готовы к локализации.
- Производительность:
    * списки «Смет» аннотируются агрегациями (без N+1);
    * чтение Excel кешируется по пути файла, mtime и индексу листа.
- Безопасность: все кастомные урлы проходят через `admin_site.admin_view`.
"""

import json
import nested_admin as na

from decimal import Decimal


from django.db import transaction, models
from django.db.models import Count
from django.urls import reverse, path
from django.utils.html import format_html
from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponseRedirect, JsonResponse

from app_outlay.forms import GroupFormSet, LinkFormSet
from app_outlay.models import (
    Estimate,
    Group,
    GroupTechnicalCardLink,
    EstimateOverheadCostLink,
)
from app_technical_cards.models import TechnicalCard as _TC

# ---------- Импорты для ENDPOINTS  ----------
import json
from app_outlay.utils_calc import calc_for_tc
from app_outlay.services.tc_matcher import TCMatcher


def _json_error(msg: str, status=400):
    return JsonResponse({"ok": False, "error": msg}, status=status)


def _json_ok(payload: dict, status=200):
    data = {"ok": True}
    data.update(payload)
    return JsonResponse(data, status=status)


# ---------- Для чтения листов  ----------
# это бы потом вынести от сюда, например в утилиты

import os
from django.core.cache import cache
from openpyxl import load_workbook


def _xlsx_cache_key(path: str, sheet_index: int) -> str:
    try:
        mtime = int(os.path.getmtime(path))
    except Exception:
        mtime = 0
    return f"outlay:xlsx:{path}:{mtime}:sheet:{sheet_index}"


def _load_full_sheet_rows(xlsx_path: str, sheet_index: int) -> list[dict]:
    """
    Возвращает ВСЕ строки листа в виде [{'row_index': int, 'cells': [..]}, ..]
    row_index — 1-based как в разметке групп.
    """
    wb = load_workbook(xlsx_path, data_only=True, read_only=True)
    try:
        ws = wb.worksheets[sheet_index]
    except IndexError:
        ws = wb.active

    rows = []
    # оценим ширину по первой непустой сотне строк
    max_cols = 0
    sample = 0
    for r in ws.iter_rows(min_row=1, max_row=min(200, ws.max_row), values_only=True):
        if any(c not in (None, "", " ") for c in r):
            max_cols = max(max_cols, len(r))
        sample += 1
        if sample >= 200:
            break
    if max_cols <= 0:
        max_cols = ws.max_column or 1

    # теперь читаем всё
    for idx, r in enumerate(
        ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True), start=1
    ):
        cells = list(r)[:max_cols]
        # нормализация текста
        norm = [(str(c).strip() if c is not None else "") for c in cells]
        rows.append({"row_index": idx, "cells": norm})
    wb.close()
    return rows


def _load_full_sheet_rows_cached(
    xlsx_path: str, sheet_index: int, ttl: int = 600
) -> list[dict]:
    """
    Обёртка над `_load_full_sheet_rows` с кешированием результатов.

    :param xlsx_path: путь к файлу .xlsx
    :param sheet_index: индекс листа
    :param ttl: время жизни кеша в секундах (дефолт: 10 минут)
    :return: список словарей строк листа
    """
    key = _xlsx_cache_key(xlsx_path, sheet_index)
    cached = cache.get(key)
    if cached is not None:
        return cached
    rows = _load_full_sheet_rows(xlsx_path, sheet_index)
    cache.set(key, rows, ttl)
    return rows


# ---------- INLINES ----------


# class EstimateOverheadCostLinkInline(na.NestedTabularInline):
class EstimateOverheadCostLinkInline(admin.TabularInline):
    """Инлайн для управления накладными расходами в смете."""

    model = EstimateOverheadCostLink
    extra = 0
    ordering = ("order", "id")

    fields = (
        # "order",
        "overhead_cost_container",
        # "is_active",
        "distribution_display",
        "snapshot_total_display",
        "current_total_display",
        # "has_changes_display",
        "applied_at",
    )

    readonly_fields = (
        "distribution_display",
        "snapshot_total_display",
        "current_total_display",
        # "has_changes_display",
        "applied_at",
    )

    autocomplete_fields = ["overhead_cost_container"]

    @admin.display(description=_("Распределение"))
    def distribution_display(self, obj):
        if not obj.pk:
            return "—"

        mat = (
            obj.snapshot_materials_percentage
            or obj.overhead_cost_container.materials_percentage
        )
        work = (
            obj.snapshot_works_percentage
            or obj.overhead_cost_container.works_percentage
        )

        return format_html(
            '<span style="font-size: 11px;">МАТ: {}% / РАБ: {}%</span>', mat, work
        )

    @admin.display(description=_("Сумма (снапшот)"))
    def snapshot_total_display(self, obj):
        if not obj.pk or not obj.snapshot_total_amount:
            return "—"
        return f"{obj.snapshot_total_amount:,.2f}"

    @admin.display(description=_("Сумма (текущая)"))
    def current_total_display(self, obj):
        if not obj.pk:
            return "—"
        total = obj.current_total_amount

        if obj.has_changes:
            return format_html(
                f'<span style="color: #856404;">{total:,.2f} ⚠️</span>',
            )
        return f"{total:,.2f}"

    # @admin.display(description=_("Изменён?"), boolean=True)
    # def has_changes_display(self, obj):
    #     if not obj.pk:
    #         return None
    #     return obj.has_changes


class GroupTechnicalCardLinkInline(admin.TabularInline):
    model = GroupTechnicalCardLink
    extra = 0
    ordering = ("order", "id")
    raw_id_fields = ("technical_card_version",)
    show_change_link = True

    fields = (
        "order",
        "technical_card_version",
        "quantity",
        "unit_display",
        "unit_cost_materials_display",
        "unit_cost_works_display",
        "unit_cost_total_display",
        "total_cost_materials_display",
        "total_cost_works_display",
        "total_cost_display",
        "pinned_at",
    )
    readonly_fields = (
        "unit_display",
        "unit_cost_materials_display",
        "unit_cost_works_display",
        "unit_cost_total_display",
        "total_cost_materials_display",
        "total_cost_works_display",
        "total_cost_display",
        "pinned_at",
    )

    @admin.display(description=_("Ед. ТК"))
    def unit_display(self, obj):
        return obj.unit or ""

    @admin.display(description=_("Цена МАТ/ед"))
    def unit_cost_materials_display(self, obj):
        v = obj.unit_cost_materials
        return "—" if v in (None, "") else f"{v:.2f}"

    @admin.display(description=_("Цена РАБ/ед"))
    def unit_cost_works_display(self, obj):
        v = obj.unit_cost_works
        return "—" if v in (None, "") else f"{v:.2f}"

    @admin.display(description=_("Итого / ед (ТК)"))
    def unit_cost_total_display(self, obj):
        v = obj.unit_cost_total
        return "—" if v in (None, "") else f"{v:.2f}"

    @admin.display(description=_("МАТ × кол-во"))
    def total_cost_materials_display(self, obj):
        v = obj.total_cost_materials
        return "—" if v in (None, "") else f"{v:.2f}"

    @admin.display(description=_("РАБ × кол-во"))
    def total_cost_works_display(self, obj):
        v = obj.total_cost_works
        return "—" if v in (None, "") else f"{v:.2f}"

    @admin.display(description=_("Итого (МАТ+РАБ) × кол-во"))
    def total_cost_display(self, obj):
        v = obj.total_cost
        return "—" if v in (None, "") else f"{v:.2f}"


# ---------- АДМИНКИ ----------

ROLE_TITLES = {
    "NAME_OF_WORK": "НАИМЕНОВАНИЕ РАБОТ/ТК",
    "UNIT": "ЕД. ИЗМ.",
    "QTY": "КОЛ-ВО",
    "UNIT_PRICE_OF_MATERIAL": "ЦЕНА МАТ/ЕД",
    "UNIT_PRICE_OF_WORK": "ЦЕНА РАБОТЫ/ЕД",
    "UNIT_PRICE_OF_MATERIALS_AND_WORKS": "ЦЕНА МАТ+РАБ/ЕД",
    "PRICE_FOR_ALL_MATERIAL": "ИТОГО МАТЕРИАЛ",
    "PRICE_FOR_ALL_WORK": "ИТОГО РАБОТА",
    "TOTAL_PRICE": "ОБЩАЯ ЦЕНА",
}
OPTIONAL_ROLE_IDS = [
    "UNIT_PRICE_OF_MATERIAL",
    "UNIT_PRICE_OF_WORK",
    "UNIT_PRICE_OF_MATERIALS_AND_WORKS",
    "PRICE_FOR_ALL_MATERIAL",
    "PRICE_FOR_ALL_WORK",
    "TOTAL_PRICE",
]


@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
    change_form_template = "admin/app_outlay/estimate_change.html"
    save_on_top = True
    list_per_page = 50
    list_display = (
        # "id",
        "name",
        "source_file",
        "currency",
        # "groups_count_annot",
        # "tc_links_count_annot",
        # "overhead_costs_count_annot",
    )
    search_fields = ("name",)
    inlines = [EstimateOverheadCostLinkInline]
    readonly_fields = (
        "source_file",
        "source_sheet_index",
    )

    # Переопределим, чтобы убрать N+1 при списковом виде
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _groups_count=Count("groups", distinct=False),
            _tc_links_count=Count("groups__techcard_links", distinct=True),
            _overhead_count=Count("overhead_cost_links", distinct=True),
        )

    # вычисляемые колонки для спискового вида
    # @admin.display(description=_("Групп"))
    # def groups_count_annot(self, obj):
    #     return obj._groups_count

    # @admin.display(description=_("ТК в смете"))
    # def tc_links_count_annot(self, obj):
    #     return obj._tc_links_count

    # @admin.display(description=_("НР"))
    # def overhead_costs_count_annot(self, obj):
    #     if hasattr(obj, "_overhead_count"):
    #         return obj._overhead_count
    #     return obj.overhead_cost_links.filter(is_active=True).count()

    # ---------- URLS: роутинг ----------
    # это нужно будет вынести отсюда. можно использовать DRF

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "technical-card-autocomplete/",
                self.admin_site.admin_view(self.tc_autocomplete),
                name="outlay_tc_autocomplete",
            ),
            path(
                "<path:object_id>/api/calc/",
                self.admin_site.admin_view(self.api_calc),
                name="estimate_calc",
            ),
            # НОВЫЙ ENDPOINT
            path(
                "<path:object_id>/api/auto-match/",
                self.admin_site.admin_view(self.api_auto_match),
                name="estimate_auto_match",
            ),
            # сохранить расчеты, создать группы, ТК
            path(
                "<path:object_id>/api/save-mappings/",
                self.admin_site.admin_view(self.api_save_mappings),
                name="estimate_save_mappings",
            ),
            path(
                "<path:object_id>/api/export-excel/",
                self.admin_site.admin_view(self.api_export_excel),
                name="estimate_export_excel",
            ),
            # НОВЫЙ ЭНДПОИНТ - страница детального анализа
            path(
                "<path:object_id>/analysis/",
                self.admin_site.admin_view(self.analysis_view),
                name="estimate_analysis",
            ),
            # API для данных графиков
            path(
                "<path:object_id>/api/analysis-data/",
                self.admin_site.admin_view(self.api_analysis_data),
                name="estimate_analysis_data",
            ),
        ]
        return custom + urls

    # ---------- ENDPOINTS: ... ----------
    # также лучше вынести из модуля, например во view|contrillers etc

    def analysis_view(self, request, object_id: str):
        """
        Страница детального анализа сметы с графиками и декомпозицией цен.
        """
        from django.template.response import TemplateResponse

        est = self.get_object(request, object_id)
        if not est:
            messages.error(request, "Смета не найдена")
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        context = dict(
            self.admin_site.each_context(request),  # ← ИСПРАВЛЕНО
            title=f"Анализ сметы: {est.name}",
            estimate=est,
            has_data=est.groups.exists(),
        )

        return TemplateResponse(
            request, "admin/app_outlay/estimate_analysis.html", context
        )

    def api_analysis_data(self, request, object_id: str):
        """
        API: данные для графиков анализа сметы.

        ✓ База — по живым ценам (_base_costs_live).
        ✓ Продажи без НР — calc_for_tc(..., overhead_context=None).
        ✓ Продажи с НР — calc_for_tc(..., overhead_context=overhead_ctx из активных контейнеров сметы).
        ✓ Итог = продажи без НР + НР (фактически: сумма «с НР»).
        ✓ Группы — по ID (не склеиваются одноимённые).
        """
        from decimal import Decimal
        from django.http import JsonResponse
        from app_outlay.models import GroupTechnicalCardLink
        from app_outlay.utils_calc import _base_costs_live, _dec, calc_for_tc

        print("\n" + "=" * 80)
        print(f"API ANALYSIS DATA - Estimate #{object_id}")
        print("=" * 80)

        est = self.get_object(request, object_id)
        if not est:
            print("❌ ОШИБКА: Смета не найдена")
            return JsonResponse({"ok": False, "error": "Смета не найдена"}, status=404)

        print(f"✓ Смета найдена: {est.name}")
        print(f"  ID: {est.id}")

        try:
            # --- связи Группа–Версия ТК
            tc_links = (
                GroupTechnicalCardLink.objects.filter(group__estimate=est)
                .select_related(
                    "technical_card_version", "technical_card_version__card", "group"
                )
                .order_by("group__order", "order")
            )
            tc_count = tc_links.count()
            print(f"\n🔗 Технические карты в смете: {tc_count}")
            if not tc_count:
                print("\n⚠️ ВОЗВРАТ: has_data=False")
                print("=" * 80 + "\n")
                return JsonResponse(
                    {
                        "ok": True,
                        "has_data": False,
                        "message": "В смете нет привязанных техкарт",
                    }
                )

            # --------------------------------------------------------------------
            # 1) Сбор контекста НР из активных контейнеров (как в detail/export)
            # --------------------------------------------------------------------
            overhead_links = est.overhead_cost_links.filter(
                is_active=True
            ).select_related("overhead_cost_container")

            total_overhead_amt = Decimal("0")
            # суммы (amount * pct) для средневзвешенного разбиения МАТ/РАБ
            amount_weighted_mat_pct = Decimal("0")
            amount_weighted_work_pct = Decimal("0")

            overhead_breakdown = []
            for ol in overhead_links:
                amount = (
                    _dec(ol.snapshot_total_amount)
                    if ol.snapshot_total_amount is not None
                    else _dec(ol.overhead_cost_container.total_amount)
                )
                mat_pct = (
                    _dec(ol.snapshot_materials_percentage)
                    if ol.snapshot_materials_percentage is not None
                    else _dec(ol.overhead_cost_container.materials_percentage)
                )
                work_pct = (
                    _dec(ol.snapshot_works_percentage)
                    if ol.snapshot_works_percentage is not None
                    else _dec(ol.overhead_cost_container.works_percentage)
                )

                total_overhead_amt += amount
                amount_weighted_mat_pct += (mat_pct or 0) * amount
                amount_weighted_work_pct += (work_pct or 0) * amount

                overhead_breakdown.append(
                    {
                        "name": ol.overhead_cost_container.name,
                        "total": float(amount),
                        "materials_part": float(
                            amount * ((mat_pct or 0) / Decimal("100"))
                        ),
                        "works_part": float(
                            amount * ((work_pct or 0) / Decimal("100"))
                        ),
                        "materials_pct": float(mat_pct or 0),
                        "works_pct": float(work_pct or 0),
                    }
                )

            if total_overhead_amt > 0:
                avg_mat_pct = amount_weighted_mat_pct / total_overhead_amt  # 0..100
                avg_work_pct = amount_weighted_work_pct / total_overhead_amt
            else:
                avg_mat_pct = Decimal("0")
                avg_work_pct = Decimal("0")

            # Общая БАЗА (живые) — нужна для корректной работы движка с НР
            total_base_mat_live = Decimal("0")
            total_base_work_live = Decimal("0")
            for link in tc_links:
                ver = link.technical_card_version
                qty = _dec(getattr(link, "quantity", 1))
                base = _base_costs_live(ver)
                total_base_mat_live += _dec(base.mat) * qty
                total_base_work_live += _dec(base.work) * qty

            overhead_context = None
            if total_overhead_amt > 0:
                overhead_context = {
                    "total_base_mat": total_base_mat_live,
                    "total_base_work": total_base_work_live,
                    "overhead_amount": total_overhead_amt,
                    "overhead_mat_pct": avg_mat_pct,  # в процентах (0..100)
                    "overhead_work_pct": avg_work_pct,  # в процентах (0..100)
                }

            print("\n💼 НР (контекст):")
            print(f"   Сумма НР: {total_overhead_amt}")
            print(f"   Средневзвеш.: МАТ%={avg_mat_pct:.2f}, РАБ%={avg_work_pct:.2f}")

            # --------------------------------------------------------------------
            # 2) Проходим по позициям и считаем (а) без НР и (б) с НР
            # --------------------------------------------------------------------
            total_base_mat = Decimal("0")
            total_base_work = Decimal("0")
            sales_mat_no_oh = Decimal("0")
            sales_work_no_oh = Decimal("0")
            sales_mat_with_oh = Decimal("0")
            sales_work_with_oh = Decimal("0")

            positions_data = []
            groups = {}  # агрегируем по group.id

            for link in tc_links:
                ver = link.technical_card_version
                if ver is None:
                    continue

                qty = _dec(getattr(link, "quantity", 1))

                # БАЗА — живые
                base = _base_costs_live(ver)
                line_base_mat = _dec(base.mat) * qty
                line_base_work = _dec(base.work) * qty
                total_base_mat += line_base_mat
                total_base_work += line_base_work

                # ПРОДАЖИ без НР
                calc0, _ = calc_for_tc(ver.card_id, float(qty), overhead_context=None)
                l0_mat = _dec(calc0.get("PRICE_FOR_ALL_MATERIAL", 0))
                l0_work = _dec(calc0.get("PRICE_FOR_ALL_WORK", 0))
                sales_mat_no_oh += l0_mat
                sales_work_no_oh += l0_work

                # ПРОДАЖИ с НР
                if overhead_context:
                    calc1, _ = calc_for_tc(
                        ver.card_id, float(qty), overhead_context=overhead_context
                    )
                    l1_mat = _dec(calc1.get("PRICE_FOR_ALL_MATERIAL", 0))
                    l1_work = _dec(calc1.get("PRICE_FOR_ALL_WORK", 0))
                else:
                    l1_mat, l1_work = l0_mat, l0_work
                sales_mat_with_oh += l1_mat
                sales_work_with_oh += l1_work

                positions_data.append(
                    {
                        "name": (ver.card.name or "")[:120],
                        "group": link.group.name,
                        "qty": float(qty),
                        "unit": ver.output_unit or "",
                        "base_mat": float(line_base_mat),
                        "base_work": float(line_base_work),
                        "final_mat": float(l0_mat),  # продажи без НР
                        "final_work": float(l0_work),  # продажи без НР
                        "total": float(l0_mat + l0_work),
                    }
                )

                # Группы по ID
                g = link.group
                if g.id not in groups:
                    groups[g.id] = {
                        "id": g.id,
                        "name": g.name,
                        "base_total": Decimal("0"),
                        "final_total": Decimal("0"),
                    }
                groups[g.id]["base_total"] += line_base_mat + line_base_work
                groups[g.id]["final_total"] += l0_mat + l0_work  # продажи без НР

            # --------------------------------------------------------------------
            # 3) Итоги/метрики
            # --------------------------------------------------------------------
            base_total = total_base_mat + total_base_work
            sales_total_no_oh = sales_mat_no_oh + sales_work_no_oh
            sales_total_with_oh = sales_mat_with_oh + sales_work_with_oh
            overhead_total_by_calc = (
                sales_total_with_oh - sales_total_no_oh
            )  # сколько реально добавлено НР

            avg_markup = (
                ((sales_total_no_oh - base_total) / base_total * 100)
                if base_total > 0
                else Decimal("0")
            )
            overhead_percent = (
                (overhead_total_by_calc / sales_total_no_oh * 100)
                if sales_total_no_oh > 0
                else Decimal("0")
            )

            # разбиение НР по Мат/Раб — из разницы «с НР» минус «без НР»
            oh_mat = sales_mat_with_oh - sales_mat_no_oh
            oh_work = sales_work_with_oh - sales_work_no_oh

            summary = {
                "base_materials": float(total_base_mat),
                "base_works": float(total_base_work),
                "base_total": float(base_total),
                "final_materials": float(sales_mat_no_oh),  # продажи без НР
                "final_works": float(sales_work_no_oh),  # продажи без НР
                "final_before_overhead": float(sales_total_no_oh),
                "overhead_total": float(overhead_total_by_calc),
                "final_with_overhead": float(sales_total_with_oh),
                "avg_markup_percent": float(avg_markup),
                "overhead_percent": float(overhead_percent),
                "positions_count": len(positions_data),
                "oh_split": {"materials": float(oh_mat), "works": float(oh_work)},
            }

            price_breakdown = {
                "labels": ["Себестоимость", "Продажи (без НР)", "Итог (с НР)"],
                "values": [
                    float(base_total),
                    float(sales_total_no_oh),
                    float(sales_total_with_oh),
                ],
            }

            groups_list = [
                {
                    "id": g["id"],
                    "name": g["name"],
                    "base_total": float(g["base_total"]),
                    "final_total": float(g["final_total"]),  # продажи без НР
                }
                for g in groups.values()
            ]
            groups_list.sort(key=lambda x: x["final_total"], reverse=True)

            materials_vs_works = {
                "labels": ["Материалы", "Работы"],
                "base": [float(total_base_mat), float(total_base_work)],
                "final": [float(sales_mat_no_oh), float(sales_work_no_oh)],  # без НР
            }
            materials_vs_works_after_oh = {
                "labels": ["Материалы", "Работы"],
                "values": [float(sales_mat_with_oh), float(sales_work_with_oh)],  # с НР
            }

            top_positions = sorted(
                positions_data, key=lambda x: x["total"], reverse=True
            )[:10]

            print("\n✅ УСПЕШНО: Возврат данных")
            print(f"   has_data: True")
            print(f"   positions_count: {len(positions_data)}")
            print("=" * 80 + "\n")

            return JsonResponse(
                {
                    "ok": True,
                    "has_data": True,
                    "summary": summary,
                    "price_breakdown": price_breakdown,
                    "top_positions": top_positions,
                    "groups_distribution": groups_list,
                    "overhead_breakdown": overhead_breakdown,
                    "materials_vs_works": materials_vs_works,
                    "materials_vs_works_after_oh": materials_vs_works_after_oh,
                }
            )

        except Exception as e:
            import traceback

            print("\n" + "=" * 80)
            print("❌❌❌ КРИТИЧЕСКАЯ ОШИБКА API ❌❌❌")
            print("=" * 80)
            print(f"Ошибка: {e}")
            print(traceback.format_exc())
            print("=" * 80 + "\n")
            return JsonResponse({"ok": False, "error": str(e)}, status=500)

    def api_export_excel(self, request, object_id: str):
        """
        Экспорт сметы с расчетами обратно в Excel.
        С детальным выводом через print() для отладки.
        """
        from openpyxl import load_workbook
        from openpyxl.styles import numbers
        from django.http import HttpResponse
        from decimal import Decimal
        import tempfile
        import os

        print("\n" + "=" * 80)
        print(f"========== НАЧАЛО ЭКСПОРТА СМЕТЫ #{object_id} ==========")
        print("=" * 80)

        # Получаем смету
        est = self.get_object(request, object_id)
        if not est:
            print("❌ ОШИБКА: Смета не найдена")
            messages.error(request, "Смета не найдена")
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        print(f"✓ Смета найдена: {est.name}")

        # Проверяем наличие исходного файла
        if not est.source_file or not est.source_file.file:
            print("❌ ОШИБКА: Исходный файл не найден")
            messages.error(request, "Исходный файл не найден")
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        print(f"✓ Исходный файл: {est.source_file.original_name}")
        print(f"  Путь: {est.source_file.file.path}")

        # Проверяем наличие разметки
        if not hasattr(est.source_file, "markup"):
            print("❌ ОШИБКА: Разметка файла не найдена")
            messages.error(request, "Разметка файла не найдена")
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        print("✓ Разметка найдена")

        try:
            markup = est.source_file.markup
            sheet_index = est.source_sheet_index or 0
            print(f"✓ Индекс листа: {sheet_index}")

            # Получаем схему колонок из разметки
            try:
                from app_estimate_imports.services.schema_service import (
                    SchemaService as _SS,
                )

                col_roles, _, _ = _SS().read_sheet_schema(markup, sheet_index)
                print("✓ Схема колонок получена через SchemaService")
            except Exception as e:
                print(f"⚠ SchemaService не сработал: {e}")
                print("  Используем fallback из annotation")
                schema = (
                    (markup.annotation or {})
                    .get("schema", {})
                    .get("sheets", {})
                    .get(str(sheet_index), {})
                )
                col_roles = schema.get("col_roles") or []
                print("✓ Схема колонок получена из annotation")

            print(f"\n📊 Всего колонок в схеме: {len(col_roles)}")
            print(f"📊 Первые 25 ролей: {col_roles[:25]}")

            if not col_roles:
                print("❌ ОШИБКА: Не удалось определить структуру колонок")
                messages.error(request, "Не удалось определить структуру колонок")
                return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

            # Загружаем Excel файл
            xlsx_path = est.source_file.file.path
            print(f"\n📂 Загрузка Excel: {xlsx_path}")

            wb = load_workbook(xlsx_path)
            print(f"✓ Файл загружен, листов: {len(wb.worksheets)}")

            try:
                ws = wb.worksheets[sheet_index]
                print(f"✓ Выбран лист: '{ws.title}'")
            except IndexError:
                ws = wb.active
                print(
                    f"⚠ Индекс {sheet_index} не найден, используем активный: '{ws.title}'"
                )

            print(f"✓ Размер листа: {ws.max_row} строк × {ws.max_column} колонок")

            # ========== ПОДГОТОВКА КОНТЕКСТА НР ==========
            print("\n" + "-" * 80)
            print("💰 НАКЛАДНЫЕ РАСХОДЫ")
            print("-" * 80)

            overhead_context = None
            overhead_links = est.overhead_cost_links.filter(
                is_active=True
            ).select_related("overhead_cost_container")

            print(f"Найдено активных НР: {overhead_links.count()}")

            if overhead_links.exists():
                total_overhead = Decimal("0")
                weighted_mat_pct = Decimal("0")
                weighted_work_pct = Decimal("0")

                for link in overhead_links:
                    amount = (
                        link.snapshot_total_amount
                        or link.overhead_cost_container.total_amount
                    )
                    mat_pct = (
                        link.snapshot_materials_percentage
                        or link.overhead_cost_container.materials_percentage
                    )
                    work_pct = (
                        link.snapshot_works_percentage
                        or link.overhead_cost_container.works_percentage
                    )

                    print(f"  • {link.overhead_cost_container.name}")
                    print(f"    Сумма: {amount}, МАТ: {mat_pct}%, РАБ: {work_pct}%")

                    total_overhead += amount
                    weighted_mat_pct += mat_pct * amount
                    weighted_work_pct += work_pct * amount

                if total_overhead > 0:
                    avg_mat_pct = weighted_mat_pct / total_overhead
                    avg_work_pct = weighted_work_pct / total_overhead
                else:
                    avg_mat_pct = Decimal("0")
                    avg_work_pct = Decimal("0")

                print(f"\n📈 ИТОГО НР: {total_overhead}")
                print(f"   Средневзвешенный МАТ%: {avg_mat_pct:.2f}")
                print(f"   Средневзвешенный РАБ%: {avg_work_pct:.2f}")

                # Рассчитываем общую базу из сохраненных ТК
                from app_outlay.utils_calc import _base_costs_live, _dec

                total_base_mat = Decimal("0")
                total_base_work = Decimal("0")

                tc_links = GroupTechnicalCardLink.objects.filter(
                    group__estimate=est
                ).select_related("technical_card_version")

                print(f"\n🔢 Подсчет базы из {tc_links.count()} ТК:")

                for idx, link in enumerate(tc_links[:5], 1):  # показываем первые 5
                    ver = link.technical_card_version
                    base = _base_costs_live(ver)
                    link_base_mat = base.mat * _dec(link.quantity)
                    link_base_work = base.work * _dec(link.quantity)
                    total_base_mat += link_base_mat
                    total_base_work += link_base_work

                    print(f"  {idx}. {ver.card.name[:40]}")
                    print(f"     МАТ: {base.mat} × {link.quantity} = {link_base_mat}")
                    print(f"     РАБ: {base.work} × {link.quantity} = {link_base_work}")

                if tc_links.count() > 5:
                    print(f"  ... и еще {tc_links.count() - 5} ТК")
                    # считаем остальные
                    for link in tc_links[5:]:
                        ver = link.technical_card_version
                        base = _base_costs_live(ver)
                        total_base_mat += base.mat * _dec(link.quantity)
                        total_base_work += base.work * _dec(link.quantity)

                print(f"\n📊 ОБЩАЯ БАЗА:")
                print(f"   МАТ: {total_base_mat}")
                print(f"   РАБ: {total_base_work}")
                print(f"   ВСЕГО: {total_base_mat + total_base_work}")

                overhead_context = {
                    "total_base_mat": total_base_mat,
                    "total_base_work": total_base_work,
                    "overhead_amount": total_overhead,
                    "overhead_mat_pct": avg_mat_pct,
                    "overhead_work_pct": avg_work_pct,
                }
                print("✓ Контекст НР создан")
            else:
                print("ℹ НР не используются")

            # ========== ПОЛУЧАЕМ ВСЕ СОПОСТАВЛЕНИЯ ==========
            print("\n" + "-" * 80)
            print("🔗 СОПОСТАВЛЕНИЯ ТК")
            print("-" * 80)

            mappings = {}  # {row_index: {tc_version, quantity}}

            all_links = GroupTechnicalCardLink.objects.filter(
                group__estimate=est
            ).select_related("technical_card_version", "technical_card_version__card")

            print(f"Всего связей ТК в смете: {all_links.count()}")

            links_with_row = 0
            links_without_row = 0

            for link in all_links:
                if link.source_row_index:
                    mappings[link.source_row_index] = {
                        "tc_version": link.technical_card_version,
                        "quantity": link.quantity,
                    }
                    links_with_row += 1
                    if links_with_row <= 10:  # показываем первые 10
                        print(
                            f"  ✓ Строка {link.source_row_index}: {link.technical_card_version.card.name[:40]} × {link.quantity}"
                        )
                else:
                    links_without_row += 1
                    if links_without_row <= 3:
                        print(
                            f"  ⚠ БЕЗ row_index: {link.technical_card_version.card.name[:40]}"
                        )

            if links_with_row > 10:
                print(f"  ... и еще {links_with_row - 10} сопоставлений")

            if links_without_row > 3:
                print(f"  ... и еще {links_without_row - 3} без row_index")

            print(f"\n📊 Итого:")
            print(f"   С row_index: {links_with_row}")
            print(f"   Без row_index: {links_without_row}")

            if not mappings:
                print("\n❌ НЕТ СОПОСТАВЛЕНИЙ ДЛЯ ЭКСПОРТА!")
                messages.warning(
                    request,
                    "⚠️ Нет сопоставлений для экспорта. Сначала выполните сопоставление и сохраните.",
                )
                wb.close()
                return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

            # ========== ЗАПОЛНЯЕМ EXCEL ==========
            print("\n" + "-" * 80)
            print("📝 ЗАПОЛНЕНИЕ EXCEL")
            print("-" * 80)

            updated_count = 0

            # Создаем маппинг роль -> индекс колонки
            role_to_col = {}
            target_roles = [
                "QTY",
                "UNIT_PRICE_OF_MATERIAL",
                "UNIT_PRICE_OF_WORK",
                "UNIT_PRICE_OF_MATERIALS_AND_WORKS",
                "PRICE_FOR_ALL_MATERIAL",
                "PRICE_FOR_ALL_WORK",
                "TOTAL_PRICE",
            ]

            for idx, role in enumerate(col_roles):
                if role in target_roles:
                    role_to_col[role] = idx
                    col_letter = chr(65 + idx) if idx < 26 else f"A{chr(65 + idx - 26)}"
                    print(f"  📌 Колонка {idx} ({col_letter}): {role}")

            print(f"\n✓ Найдено колонок для заполнения: {len(role_to_col)}")

            if not role_to_col:
                print("❌ НЕТ РАЗМЕЧЕННЫХ КОЛОНОК ДЛЯ ЗАПИСИ!")
                messages.error(request, "❌ Нет размеченных колонок для записи данных")
                wb.close()
                return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

            # Проходим по всем сопоставлениям
            print(f"\n🔄 Обработка {len(mappings)} сопоставлений:\n")

            for idx, (row_index, mapping) in enumerate(mappings.items(), 1):
                tc_version = mapping["tc_version"]
                quantity = mapping["quantity"]

                print(f"{idx}. СТРОКА {row_index} {'='*60}")
                print(f"   ТК: {tc_version.card.name}")
                print(f"   ID карточки: {tc_version.card_id}")
                print(f"   Количество: {quantity}")

                if "QTY" in role_to_col:
                    col_idx = role_to_col["QTY"]
                    excel_row = row_index
                    excel_col = col_idx + 1

                    col_letter = (
                        chr(65 + col_idx)
                        if col_idx < 26
                        else f"A{chr(65 + col_idx - 26)}"
                    )
                    cell_address = f"{col_letter}{excel_row}"

                    try:
                        cell = ws.cell(row=excel_row, column=excel_col)
                        old_qty = cell.value

                        # Записываем количество как число
                        cell.value = float(quantity)
                        cell.number_format = "#,##0.000"

                        print(
                            f"   📊 {cell_address} (QTY): {old_qty} → {float(quantity):.3f}"
                        )
                    except Exception as e:
                        print(f"   ❌ Ошибка записи количества в {cell_address}: {e}")

                # Вызываем расчет с НР
                try:
                    calc, _ = calc_for_tc(
                        tc_version.card_id, quantity, overhead_context=overhead_context
                    )
                    print(f"   ✓ Расчет выполнен:")
                    for key, val in calc.items():
                        print(f"      {key}: {val}")
                except Exception as e:
                    print(f"   ❌ ОШИБКА РАСЧЕТА: {e}")
                    import traceback

                    print(traceback.format_exc())
                    continue

                # Записываем значения в соответствующие колонки
                cells_written = 0
                for role, value in calc.items():
                    if role in role_to_col:
                        col_idx = role_to_col[role]
                        excel_row = row_index
                        excel_col = col_idx + 1

                        col_letter = (
                            chr(65 + col_idx)
                            if col_idx < 26
                            else f"A{chr(65 + col_idx - 26)}"
                        )
                        cell_address = f"{col_letter}{excel_row}"

                        try:
                            cell = ws.cell(row=excel_row, column=excel_col)
                            old_value = cell.value

                            # Записываем значение как число
                            cell.value = float(value)
                            cell.number_format = "#,##0.000"

                            print(
                                f"      ✓ {cell_address}: {old_value} → {float(value):.3f}"
                            )
                            cells_written += 1

                        except Exception as e:
                            print(f"      ❌ Ошибка записи в {cell_address}: {e}")

                if cells_written > 0:
                    updated_count += 1
                    print(f"   ✓ Записано ячеек: {cells_written}")
                else:
                    print(f"   ⚠ НИ ОДНОЙ ЯЧЕЙКИ НЕ ЗАПИСАНО!")

                print()  # пустая строка между записями

                # Показываем только первые 5 детально
                if idx >= 5 and len(mappings) > 5:
                    print(
                        f"... обрабатываются остальные {len(mappings) - 5} строк ...\n"
                    )
                    # обрабатываем остальные без детального вывода
                    for row_index2, mapping2 in list(mappings.items())[5:]:
                        tc_version2 = mapping2["tc_version"]
                        quantity2 = mapping2["quantity"]
                        try:
                            calc2, _ = calc_for_tc(
                                tc_version2.card_id,
                                quantity2,
                                overhead_context=overhead_context,
                            )
                            for role, value in calc2.items():
                                if role in role_to_col:
                                    col_idx = role_to_col[role]
                                    excel_row = row_index2
                                    excel_col = col_idx + 1
                                    cell = ws.cell(row=excel_row, column=excel_col)
                                    cell.value = float(value)
                                    cell.number_format = "#,##0.000"
                            updated_count += 1
                        except Exception as e:
                            print(f"   ❌ Ошибка в строке {row_index2}: {e}")
                    break

            print("\n" + "=" * 80)
            print(f"✅ ИТОГО ОБРАБОТАНО СТРОК: {updated_count} из {len(mappings)}")
            print("=" * 80)

            # ========== СОХРАНЯЕМ ФАЙЛ ==========
            print("\n💾 Сохранение файла...")

            temp_dir = tempfile.gettempdir()
            original_name = os.path.splitext(est.source_file.original_name)[0]
            output_filename = f"{original_name}_calculated.xlsx"
            temp_path = os.path.join(temp_dir, output_filename)

            print(f"   Временный путь: {temp_path}")

            wb.save(temp_path)
            print(f"   ✓ Файл сохранен")

            wb.close()
            print(f"   ✓ Workbook закрыт")

            # Читаем и отправляем
            with open(temp_path, "rb") as f:
                file_content = f.read()
                file_size = len(file_content)
                print(f"   ✓ Размер: {file_size:,} байт")

                response = HttpResponse(
                    file_content,
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                response["Content-Disposition"] = (
                    f'attachment; filename="{output_filename}"'
                )

            # Удаляем временный файл
            try:
                os.unlink(temp_path)
                print(f"   ✓ Временный файл удален")
            except Exception as e:
                print(f"   ⚠ Не удалось удалить временный файл: {e}")

            messages.success(
                request,
                f"✅ Экспорт выполнен успешно! Обновлено строк: {updated_count}",
            )

            print("\n" + "=" * 80)
            print("✅ ЭКСПОРТ ЗАВЕРШЕН УСПЕШНО")
            print("=" * 80 + "\n")

            return response

        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            print("\n" + "=" * 80)
            print("❌❌❌ КРИТИЧЕСКАЯ ОШИБКА ЭКСПОРТА ❌❌❌")
            print("=" * 80)
            print(f"Ошибка: {e}")
            print(error_details)
            print("=" * 80 + "\n")
            messages.error(request, f"Ошибка экспорта: {e!r}")
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

    def api_calc(self, request, object_id: str):
        """
        API для расчета показателей по версии ТК с учетом накладных расходов сметы.

        GET параметры:
        - tc: ID технической карты
        - qty: количество

        Возвращает расчеты с учетом НР, если они есть у сметы.
        """
        try:
            tc_id = int(request.GET.get("tc", "0"))
            qty_raw = (request.GET.get("qty") or "0").replace(",", ".")
            qty = float(qty_raw)
            if tc_id <= 0 or qty < 0:
                return _json_error(_("Некорректные параметры"), 400)
        except Exception:
            return _json_error(_("Некорректные параметры"), 400)

        # Получаем смету для расчета контекста НР
        est = self.get_object(request, object_id)
        if not est:
            return _json_error(_("Смета не найдена"), 404)

        # ------- РАСЧЕТ КОНТЕКСТА НР -------
        overhead_context = None

        # 1. Получаем активные НР сметы
        overhead_links = est.overhead_cost_links.filter(is_active=True).select_related(
            "overhead_cost_container"
        )

        if overhead_links.exists():
            # 2. Суммируем все НР
            total_overhead = Decimal("0")
            weighted_mat_pct = Decimal("0")
            weighted_work_pct = Decimal("0")

            for link in overhead_links:
                amount = (
                    link.snapshot_total_amount
                    or link.overhead_cost_container.total_amount
                )
                mat_pct = (
                    link.snapshot_materials_percentage
                    or link.overhead_cost_container.materials_percentage
                )
                work_pct = (
                    link.snapshot_works_percentage
                    or link.overhead_cost_container.works_percentage
                )

                total_overhead += amount
                weighted_mat_pct += mat_pct * amount
                weighted_work_pct += work_pct * amount

            # Средневзвешенные проценты распределения
            if total_overhead > 0:
                avg_mat_pct = weighted_mat_pct / total_overhead
                avg_work_pct = weighted_work_pct / total_overhead
            else:
                avg_mat_pct = Decimal("0")
                avg_work_pct = Decimal("0")

            # 3. Рассчитываем общую базу из сохраненных ТК в смете
            from app_outlay.utils_calc import _base_costs_live, _dec

            total_base_mat = Decimal("0")
            total_base_work = Decimal("0")

            # Получаем все связи ТК в смете
            tc_links = GroupTechnicalCardLink.objects.filter(
                group__estimate=est
            ).select_related("technical_card_version")

            for link in tc_links:
                ver = link.technical_card_version
                base = _base_costs_live(ver)

                # Умножаем на количество для этой ТК в смете
                total_base_mat += base.mat * _dec(link.quantity)
                total_base_work += base.work * _dec(link.quantity)

            # Формируем контекст НР
            overhead_context = {
                "total_base_mat": total_base_mat,
                "total_base_work": total_base_work,
                "overhead_amount": total_overhead,
                "overhead_mat_pct": avg_mat_pct,
                "overhead_work_pct": avg_work_pct,
            }

        # ------- РАСЧЕТ С УЧЕТОМ НР -------
        calc, order = calc_for_tc(tc_id, qty, overhead_context=overhead_context)
        resp_calc = {k: float(v) for k, v in calc.items()}
        return _json_ok({"calc": resp_calc, "order": order})

    def tc_autocomplete(self, request, *args, **kwargs):
        """Простой автокомплит по ТК."""

        # Для ручного поиска (GET)
        if request.method == "GET":
            from app_technical_cards.models import TechnicalCard

            q = (request.GET.get("q") or "").strip()
            qs = TechnicalCard.objects.all()

            if q:
                qs = qs.filter(name__icontains=q)

            data = [{"id": obj.pk, "text": obj.name} for obj in qs[:20]]
            return JsonResponse({"results": data})

        # Для батч-автосопоставления (POST)
        if request.method == "POST":
            try:
                if (
                    request.content_type
                    and "application/json" not in request.content_type
                ):
                    return _json_error(_("Ожидается JSON"), 400)
                data = json.loads(request.body or b"{}")
                items = data.get("items") or []
                if not isinstance(items, list) or not items:
                    return _json_error(_("Нет элементов для сопоставления"), 400)
                matched = TCMatcher.batch_match(items)
                return _json_ok({"results": matched})
            except Exception as e:
                return _json_error(str(e), 500)

        return _json_error(_("Метод не разрешён"), 405)

    def api_auto_match(self, request, object_id: str):
        """API для автоматического сопоставления ТК."""
        try:
            # Получаем данные из POST
            data = json.loads(request.body)
            items = data.get("items", [])

            if not items:
                return JsonResponse({"ok": False, "error": "no_items"}, status=400)

            # Выполняем сопоставление
            matched = TCMatcher.batch_match(items)

            return JsonResponse({"ok": True, "results": matched})

        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=500)

    def api_save_mappings(self, request, object_id: str):
        """Сохранить сопоставления ТК в базу данных."""
        if request.method != "POST":
            return _json_error(_("Метод не разрешён"), 405)

        try:
            est = self.get_object(request, object_id)
            if not est:
                return _json_error(_("Смета не найдена"), 404)

            data = json.loads(request.body)
            mappings = data.get("mappings", [])
            deletions = data.get("deletions", [])  # НОВОЕ
            print(f"[DEBUG] deletions --> {deletions}")

            if not mappings and not deletions:
                return _json_error(_("Нет данных для сохранения"), 400)

            from app_technical_cards.models import TechnicalCard

            with transaction.atomic():
                created_count = 0
                updated_count = 0
                deleted_count = 0  # НОВОЕ

                # НОВОЕ: Удаляем сопоставления
                if deletions:
                    deleted_links = GroupTechnicalCardLink.objects.filter(
                        group__estimate=est, source_row_index__in=deletions
                    )
                    deleted_count = deleted_links.count()
                    deleted_links.delete()

                    print(
                        f"Удалено {deleted_count} сопоставлений для строк: {deletions}"
                    )

                # Группируем по секциям
                by_section = {}
                for m in mappings:
                    section = m.get("section", "Без группы")
                    if section not in by_section:
                        by_section[section] = []
                    by_section[section].append(m)

                # Кеш созданных групп для избежания дублей
                groups_cache = {}

                def get_or_create_group_hierarchy(
                    section_path: str, order_hint: int = 0
                ):
                    """
                    Создаёт иерархию групп по пути вида "Родитель / Дочерняя / Внучатая".
                    Возвращает самую глубокую группу.
                    """
                    if section_path in groups_cache:
                        return groups_cache[section_path]

                    # Разбиваем путь на части
                    parts = [p.strip() for p in section_path.split("/")]

                    parent = None
                    current_path = ""

                    for idx, part in enumerate(parts):
                        if not part:
                            continue

                        # Строим полный путь до текущего уровня
                        if current_path:
                            current_path += f" / {part}"
                        else:
                            current_path = part

                        # Проверяем кеш
                        if current_path in groups_cache:
                            parent = groups_cache[current_path]
                            continue

                        # Создаём или находим группу
                        group, created = Group.objects.get_or_create(
                            estimate=est,
                            name=part,
                            parent=parent,
                            defaults={"order": order_hint + idx},
                        )

                        groups_cache[current_path] = group
                        parent = group

                    return parent

                # Обрабатываем каждую секцию
                for section_idx, (section_name, items) in enumerate(by_section.items()):
                    # Получаем или создаём иерархию групп
                    group = get_or_create_group_hierarchy(
                        section_name, order_hint=section_idx * 100
                    )

                    if not group:
                        continue

                    # Обрабатываем каждую строку в секции
                    for idx, item in enumerate(items):
                        tc_id = item.get("tc_id")
                        quantity = item.get("quantity", 0)
                        row_index = item.get("row_index")

                        if not tc_id or quantity <= 0:
                            continue

                        try:
                            # Получаем карточку и её последнюю опубликованную версию
                            tc_card = TechnicalCard.objects.get(id=tc_id)
                            tc_version = (
                                tc_card.versions.filter(is_published=True)
                                .order_by("-created_at")
                                .first()
                            )

                            if not tc_version:
                                continue

                            # Проверяем существование связи с таким же source_row_index
                            existing_link = GroupTechnicalCardLink.objects.filter(
                                group=group, source_row_index=row_index
                            ).first()

                            if existing_link:
                                # Обновляем существующую запись
                                existing_link.technical_card_version = tc_version
                                existing_link.quantity = quantity
                                existing_link.order = idx
                                existing_link.save()
                                updated_count += 1
                            else:
                                # Создаём новую запись
                                GroupTechnicalCardLink.objects.create(
                                    group=group,
                                    technical_card_version=tc_version,
                                    quantity=quantity,
                                    order=idx,
                                    source_row_index=row_index,
                                )
                                created_count += 1

                        except TechnicalCard.DoesNotExist:
                            continue

                return _json_ok(
                    {
                        "created": created_count,
                        "updated": updated_count,
                        "deleted": deleted_count,  # НОВОЕ
                        "total": created_count + updated_count,
                    }
                )

        except Exception as e:
            import traceback

            traceback.print_exc()
            return _json_error(str(e), 500)

    # ---------- ВСПОМОГАТЕЛЬНОЕ: вытаскиваем индексы колонок по ролям ----------
    def _idxs(self, col_roles: list[str], role: str) -> list[int]:
        return [i for i, r in enumerate(col_roles or []) if r == role]

    def _cell(self, row: dict, idx: int) -> str:
        cells = row.get("cells") or []
        return (cells[idx] if 0 <= idx < len(cells) else "") or ""

    # ---------- ВСПОМОГАТЕЛЬНОЕ: детект ТК из ПОЛНЫХ строк ----------
    def _detect_tc_rows_from_rows(
        self,
        rows: list[dict],
        col_roles: list[str],
        unit_allow_set: set[str],
        require_qty: bool,
    ) -> list[dict]:
        name_cols = self._idxs(col_roles, "NAME_OF_WORK")
        unit_cols = self._idxs(col_roles, "UNIT")
        qty_cols = self._idxs(col_roles, "QTY")

        def first_text(row, idxs):
            for i in idxs:
                t = self._cell(row, i).strip()
                if t:
                    return t
            return ""

        def qty_ok(row):
            if not require_qty:
                return True
            for i in qty_cols:
                raw = self._cell(row, i).replace(" ", "").replace(",", ".")
                try:
                    if float(raw) > 0:
                        return True
                except Exception:
                    pass
            return False

        def normalize_unit(u: str) -> str:
            s = (u or "").lower().strip()
            s = s.replace("\u00b2", "2").replace("\u00b3", "3")
            compact = "".join(ch for ch in s if ch not in " .,")
            import re

            if re.fullmatch(r"(м\^?2|м2|квм|мкв|квадратн\w*метр\w*)", compact or ""):
                return "м2"
            if re.fullmatch(r"(м\^?3|м3|кубм|мкуб|кубическ\w*метр\w*)", compact or ""):
                return "м3"
            if re.fullmatch(r"(шт|штука|штуки|штук)", compact or ""):
                return "шт"
            if re.fullmatch(r"(пм|погм|погонныйметр|погонныхметров)", compact or ""):
                return "пм"
            if re.fullmatch(r"(компл|комплект|комплекта|комплектов)", compact or ""):
                return "компл"
            return compact

        tcs = []
        for row in rows:
            name = first_text(row, name_cols)
            unit_raw = first_text(row, unit_cols)
            unit = normalize_unit(unit_raw)
            if not name or not unit:
                continue
            if unit_allow_set and unit not in unit_allow_set:
                continue
            if not qty_ok(row):
                continue
            # qty для превью (может быть пустым)
            qty_val = first_text(row, qty_cols)
            tcs.append(
                {
                    "row_index": row.get("row_index"),
                    "name": name,
                    "unit": unit_raw,
                    "qty": qty_val,
                }
            )
        return tcs

    # ---------- ВСПОМОГАТЕЛЬНОЕ: собираем строки сопоставления (таблица) ----------

    def _collect_excel_candidates_from_rows(
        self, rows: list[dict], col_roles: list[str]
    ) -> list[dict]:
        name_cols = self._idxs(col_roles, "NAME_OF_WORK")
        unit_cols = self._idxs(col_roles, "UNIT")
        qty_cols = self._idxs(col_roles, "QTY")

        def first_text(row, idxs):
            for i in idxs:
                t = self._cell(row, i).strip()
                if t:
                    return t
            return ""

        # опциональные колонки: соберём индекс для каждой роли, если есть
        opt_idx = {
            rid: (self._idxs(col_roles, rid)[0] if self._idxs(col_roles, rid) else None)
            for rid in OPTIONAL_ROLE_IDS
        }

        out = []
        for row in rows:
            name = first_text(row, name_cols)
            unit = first_text(row, unit_cols)
            if not name and not unit:
                continue
            qty = first_text(row, qty_cols)
            excel_optional = {}
            for rid, ci in opt_idx.items():
                excel_optional[rid] = self._cell(row, ci) if ci is not None else ""
            out.append(
                {
                    "row_index": row.get("row_index"),
                    "name": name,
                    "unit": unit,
                    "qty": qty,
                    "excel_optional": excel_optional,
                }
            )
        return out

    # ---------- ВСПОМОГАТЕЛЬНОЕ: группы из annotation (толерантно) ----------
    def _load_groups_from_annotation(
        self, annotation: dict, sheet_i: int
    ) -> list[dict]:
        sheet_key = str(sheet_i)
        groups = []

        # Вариант A: annotation["schema"]["sheets"][sheet]["groups"]
        root = (annotation or {}).get("schema", {}).get("sheets", {}).get(sheet_key, {})
        if isinstance(root, dict) and isinstance(root.get("groups"), list):
            groups = root["groups"]

        # Фолбэк: annotation["groups"][sheet]
        if not groups:
            alt = (annotation or {}).get("groups", {}).get(sheet_key)
            if isinstance(alt, list):
                groups = alt
            elif isinstance(alt, dict) and isinstance(alt.get("items"), list):
                groups = alt["items"]

        # нормализация
        norm = []
        for g in groups or []:
            uid = g.get("uid") or g.get("id") or g.get("gid")
            if not uid:
                continue
            color = g.get("color") or "#e0f7fa"
            parent = g.get("parent_uid") or g.get("parent") or g.get("parentId")
            rows = g.get("rows") or g.get("ranges") or []
            rr = []
            for r in rows:
                if isinstance(r, (list, tuple)) and len(r) >= 2:
                    try:
                        rr.append([int(r[0]), int(r[1])])
                    except Exception:
                        pass
            norm.append(
                {
                    "uid": uid,
                    "name": g.get("name") or g.get("title") or "Группа",
                    "color": color,
                    "parent_uid": parent,
                    "rows": rr,
                }
            )
        return norm

    def _assign_tc_to_deepest_group(
        self, groups: list[dict], tcs: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """Возвращает (tree, loose). tree — список корневых групп с children и tcs."""
        by_id = {g["uid"]: g for g in groups}

        # глубина
        def depth(uid):
            d = 0
            cur = by_id.get(uid)
            while cur and cur.get("parent_uid"):
                d += 1
                cur = by_id.get(cur["parent_uid"])
            return d

        for g in groups:
            g["_depth"] = depth(g["uid"])

        def covered(g, row_idx: int) -> bool:
            for s, e in g.get("rows") or []:
                if s <= row_idx <= e:
                    return True
            return False

        # дерево групп
        children = {g["uid"]: [] for g in groups}
        roots = []
        for g in groups:
            pid = g.get("parent_uid")
            if pid and pid in children:
                children[pid].append(g)
            else:
                roots.append(g)

        # прикрепим ТК к самой глубокой накрывающей группе
        tcs_by_group = {g["uid"]: [] for g in groups}
        loose = []
        for tc in tcs:
            row_idx = tc.get("row_index")
            cands = [g for g in groups if covered(g, row_idx)]
            if cands:
                cands.sort(key=lambda x: x["_depth"])
                tcs_by_group[cands[-1]["uid"]].append(tc)
            else:
                loose.append(tc)

        # соберём дерево для вывода
        def build(u):
            node = by_id[u].copy()
            node["children"] = [build(ch["uid"]) for ch in children[u]]
            node["tcs"] = tcs_by_group[u]
            return node

        tree = [build(r["uid"]) for r in roots]
        return tree, loose

    # ---------- ПРЕДСТАВЛЕНИЯ: переопределенные представления ----------

    def render_change_form(
        self, request, context, add=False, change=False, form_url="", obj=None
    ):
        # на стандартный add оставляем дефолтное поведение
        if add or obj is None:
            return super().render_change_form(
                request, context, add, change, form_url, obj
            )

        # ========== ГРУППЫ И ТК ==========
        group_qs = Group.objects.filter(estimate=obj).order_by(
            "parent_id", "order", "id"
        )
        link_qs = (
            GroupTechnicalCardLink.objects.filter(group__estimate=obj)
            .select_related(
                "group", "technical_card_version", "technical_card_version__card"
            )
            .order_by("group_id", "order", "id")
        )

        # Создаём дефолтную группу если её нет
        if not group_qs.exists():
            Group.objects.get_or_create(
                estimate=obj,
                parent=None,
                defaults={"name": "Общий раздел", "order": 0},
            )
            group_qs = Group.objects.filter(estimate=obj).order_by(
                "parent_id", "order", "id"
            )

        # ========== НАКЛАДНЫЕ РАСХОДЫ ==========
        overhead_qs = (
            EstimateOverheadCostLink.objects.filter(estimate=obj)
            .select_related("overhead_cost_container")
            .order_by("order", "id")
        )

        # POST: валидируем и сохраняем формсеты
        if request.method == "POST":
            gfs = GroupFormSet(request.POST, queryset=group_qs, prefix="grp")
            lfs = LinkFormSet(request.POST, queryset=link_qs, prefix="lnk")

            # Формсет для накладных расходов
            from django.forms import modelformset_factory

            OverheadFormSet = modelformset_factory(
                EstimateOverheadCostLink,
                fields=["order", "overhead_cost_container", "is_active"],
                extra=1,
                can_delete=True,
            )
            ofs = OverheadFormSet(request.POST, queryset=overhead_qs, prefix="overhead")

            # Валидация всех формсетов
            if gfs.is_valid() and lfs.is_valid() and ofs.is_valid():
                with transaction.atomic():
                    gfs.save()
                    lfs.save()

                    # Сохраняем накладные расходы
                    for form in ofs.forms:
                        if form.cleaned_data and not form.cleaned_data.get(
                            "DELETE", False
                        ):
                            instance = form.save(commit=False)
                            instance.estimate = obj
                            instance.save()

                    # Удаляем помеченные
                    for form in ofs.deleted_forms:
                        if form.instance.pk:
                            form.instance.delete()

                self.message_user(
                    request, _("Изменения сохранены"), level=messages.SUCCESS
                )
                return HttpResponseRedirect(request.path)
            else:
                self.message_user(
                    request, _("Исправьте ошибки в форме"), level=messages.ERROR
                )
        else:
            gfs = GroupFormSet(queryset=group_qs, prefix="grp")
            lfs = LinkFormSet(queryset=link_qs, prefix="lnk")

            # Формсет для накладных расходов (GET)
            from django.forms import modelformset_factory

            OverheadFormSet = modelformset_factory(
                EstimateOverheadCostLink,
                fields=["order", "overhead_cost_container", "is_active"],
                extra=1,
                can_delete=True,
            )
            ofs = OverheadFormSet(queryset=overhead_qs, prefix="overhead")

        # ========== ПОСТРОЕНИЕ ДЕРЕВА ГРУПП ==========
        groups = list(group_qs)
        children = {}
        for g in groups:
            children.setdefault(g.parent_id, []).append(g)
        for lst in children.values():
            lst.sort(key=lambda x: (x.order, x.id))

        gform_by_id = {f.instance.pk: f for f in gfs.forms}
        lforms_by_gid = {}
        for f in lfs.forms:
            lforms_by_gid.setdefault(f.instance.group_id, []).append((f.instance, f))

        def build(parent_id):
            out = []
            for g in children.get(parent_id, []):
                out.append(
                    {
                        "group": g,
                        "group_form": gform_by_id.get(g.pk),
                        "links": lforms_by_gid.get(
                            g.pk, []
                        ),  # [(link_obj, link_form), ...]
                        "children": build(g.pk),
                    }
                )
            return out

        tree = build(None)

        # ========== КОНТЕКСТ ==========
        context.update(
            {
                "title": f"Смета: {obj.name}",
                "tree": tree,
                "group_formset": gfs,
                "link_formset": lfs,
                "overhead_formset": ofs,  # НОВОЕ
                "overhead_links": list(
                    overhead_qs
                ),  # НОВОЕ: для удобного доступа в шаблоне
                "list_url": reverse(
                    f"admin:{Estimate._meta.app_label}_{Estimate._meta.model_name}_changelist"
                ),
            }
        )
        return super().render_change_form(request, context, add, change, form_url, obj)

    def change_view(self, request, object_id, form_url="", extra_context=None):

        extra = dict(extra_context or {})
        est = self.get_object(request, object_id)

        # Контекст по умолчанию
        excel_candidates: list[dict] = []
        table_sections: list[dict] = []
        optional_cols: list[dict] = []
        present_optional: list[str] = []
        role_titles = ROLE_TITLES  # константа сверху файла

        if (
            est
            and est.source_file_id
            and hasattr(est.source_file, "parse_result")
            and hasattr(est.source_file, "markup")
        ):
            pr = est.source_file.parse_result
            markup = est.source_file.markup
            sheet_i = est.source_sheet_index or 0

            # --- 1) Схема листа: роли колонок, allow-юниты, требование qty>0
            # Пытаемся через сервис, иначе — из annotation с нормализацией.
            unit_allow_set = set()
            require_qty = False
            col_roles: list[str] = []

            def _normalize_unit(u: str) -> str:
                s = (u or "").lower().strip()
                s = s.replace("\u00b2", "2").replace("\u00b3", "3")
                compact = "".join(ch for ch in s if ch not in " .,")
                import re

                if re.fullmatch(
                    r"(м\^?2|м2|квм|мкв|квадратн\w*метр\w*)", compact or ""
                ):
                    return "м2"
                if re.fullmatch(
                    r"(м\^?3|м3|кубм|мкуб|кубическ\w*метр\w*)", compact or ""
                ):
                    return "м3"
                if re.fullmatch(r"(шт|штука|штуки|штук)", compact or ""):
                    return "шт"
                if re.fullmatch(
                    r"(пм|погм|погонныйметр|погонныхметров)", compact or ""
                ):
                    return "пм"
                if re.fullmatch(
                    r"(компл|комплект|комплекта|комплектов)", compact or ""
                ):
                    return "компл"
                return compact

            try:
                # если у тебя есть сервис схем
                from app_estimate_imports.services.schema_service import (
                    SchemaService as _SS,
                )

                col_roles, unit_allow_set, require_qty = _SS().read_sheet_schema(
                    markup, sheet_i
                )
                unit_allow_set = set(
                    _normalize_unit(u) for u in (unit_allow_set or set())
                )
            except Exception:
                sch = (
                    (markup.annotation or {})
                    .get("schema", {})
                    .get("sheets", {})
                    .get(str(sheet_i), {})
                )
                col_roles = sch.get("col_roles") or []
                raw = (sch.get("unit_allow_raw") or "") if isinstance(sch, dict) else ""
                unit_allow_set = set()
                for part in (raw or "").split(","):
                    n = _normalize_unit(part)
                    if n:
                        unit_allow_set.add(n)
                require_qty = bool(sch.get("require_qty"))

            # --- 2) Загружаем ПОЛНЫЙ лист Excel (никаких ограничений)
            xlsx_path = getattr(est.source_file.file, "path", None) or (
                (pr.data or {}).get("file") or {}
            ).get("path")
            if xlsx_path:
                rows_full = _load_full_sheet_rows_cached(xlsx_path, sheet_i)
            else:
                # фолбэк на parse_result, если файла нет
                rows_full = ((pr.data or {}).get("sheets") or [{}])[sheet_i].get(
                    "rows"
                ) or []

            # --- 3) Детектируем кандидатов ТК по тем же правилам, что и в grid.html
            # ВАЖНО: здесь НЕ ограничиваемся группами — берём весь лист.
            tcs = self._detect_tc_rows_from_rows(
                rows_full, col_roles, unit_allow_set, require_qty
            )

            # --- 4) Группы/подгруппы из annotation и раскладка ТК
            groups = self._load_groups_from_annotation(markup.annotation or {}, sheet_i)
            tree, loose = self._assign_tc_to_deepest_group(groups, tcs)

            # --- 5) Собираем «кандидатов» для табличного вида
            # Берём только те строки, которые прошли детект (без «шума»).
            allowed_rows = {tc["row_index"] for tc in tcs}
            excel_all = self._collect_excel_candidates_from_rows(rows_full, col_roles)
            excel_candidates = [
                it for it in excel_all if it["row_index"] in allowed_rows
            ]

            # --- 6) Опциональные колонки: показываем только размеченные
            present_optional = [rid for rid in OPTIONAL_ROLE_IDS if rid in col_roles]
            optional_cols = [
                {"id": rid, "title": role_titles.get(rid, rid)}
                for rid in present_optional
            ]
            # xls-значения опций — строго в порядке колонок optional_cols
            for it in excel_candidates:
                raw = it.get("excel_optional") or {}
                it["opt_values"] = [raw.get(r["id"], "") for r in optional_cols]

            # --- 7) Собираем секции таблицы:
            #     - если есть группы: секция на каждую + «Без группы» для остатка
            #     - если групп нет вообще: одна секция «Без группы» со всеми ТК
            cand_by_row = {it["row_index"]: it for it in excel_candidates}
            table_sections = []

            if groups:
                # раскладываем по дереву
                def _flatten(node: dict, parent_path: str | None = None):
                    path = node.get("name") or "Группа"
                    path = path if parent_path is None else f"{parent_path} / {path}"
                    items = []
                    for tc in node.get("tcs") or []:
                        ci = cand_by_row.get(tc["row_index"])
                        if ci:
                            items.append(ci)
                    if items:
                        table_sections.append(
                            {
                                "path": path,
                                "color": node.get("color") or "#eef",
                                "items": items,
                            }
                        )
                    for ch in node.get("children") or []:
                        _flatten(ch, path)

                for root in tree or []:
                    _flatten(root)

                # остаток без группы
                loose_items = []
                for tc in loose or []:
                    ci = cand_by_row.get(tc["row_index"])
                    if ci:
                        loose_items.append(ci)
                if loose_items:
                    table_sections.append(
                        {"path": "Без группы", "color": "#f0f4f8", "items": loose_items}
                    )
            else:
                # групп нет — одна секция со всеми найденными ТК
                if excel_candidates:
                    table_sections = [
                        {
                            "path": "Без группы",
                            "color": "#f0f4f8",
                            "items": excel_candidates,
                        }
                    ]
                else:
                    table_sections = []

            # --- 8) Загружаем существующие сопоставления из БД
            existing_mappings = {}  # {row_index: {tc_id, tc_name, quantity}}

            if est:
                # Получаем все связи для этой сметы
                links_qs = GroupTechnicalCardLink.objects.filter(
                    group__estimate=est
                ).select_related(
                    "group", "technical_card_version", "technical_card_version__card"
                )

                # НОВАЯ ЛОГИКА: прямое сопоставление по source_row_index
                for link in links_qs:
                    if link.source_row_index:  # Если есть привязка к строке Excel
                        existing_mappings[link.source_row_index] = {
                            "tc_id": link.technical_card_version.card_id,
                            "tc_name": link.technical_card_version.card.name,
                            "quantity": float(link.quantity),
                        }

        base_materials = Decimal("0.00")
        base_works = Decimal("0.00")
        overhead_calc = None
        overhead_calc_json = "null"

        if est:
            # Суммируем все ТК в смете
            links = GroupTechnicalCardLink.objects.filter(
                group__estimate=est
            ).select_related("technical_card_version")

            for link in links:
                base_materials += link.total_cost_materials or Decimal("0.00")
                base_works += link.total_cost_works or Decimal("0.00")

            # Получаем расчёт с НР
            overhead_calc = est.calculate_totals_with_overhead(
                base_materials, base_works
            )

            # НОВОЕ: Сериализуем для JavaScript
            if overhead_calc:
                overhead_calc_json = json.dumps(
                    {
                        "base_materials": float(overhead_calc["base_materials"]),
                        "base_works": float(overhead_calc["base_works"]),
                        "base_total": float(overhead_calc["base_total"]),
                        "overhead_materials": float(
                            overhead_calc["overhead_materials"]
                        ),
                        "overhead_works": float(overhead_calc["overhead_works"]),
                        "overhead_total": float(overhead_calc["overhead_total"]),
                        "final_materials": float(overhead_calc["final_materials"]),
                        "final_works": float(overhead_calc["final_works"]),
                        "final_total": float(overhead_calc["final_total"]),
                    },
                    ensure_ascii=False,
                )

        tc_change_url_zero = reverse(
            f"admin:{_TC._meta.app_label}_{_TC._meta.model_name}_change",
            args=[0],
        )

        # --- 8) Отдаём контекст в шаблон
        extra.update(
            {
                "excel_candidates": excel_candidates,  # если захочешь отрисовать плоско
                "table_sections": table_sections,  # основной вывод секциями
                "optional_cols": optional_cols,  # [{id, title}]
                "calc_order_json": json.dumps(
                    [c["id"] for c in optional_cols], ensure_ascii=False
                ),
                "role_titles": role_titles,
                "tc_autocomplete_url": reverse("admin:outlay_tc_autocomplete"),
                "table_colspan": 4
                + len(optional_cols),  # для colspan в заголовках секций
                "tc_preview": {"ready": False},  # чтобы шаблон не ожидал старую панель
                "existing_mappings_json": json.dumps(
                    existing_mappings, ensure_ascii=False
                ),
                "overhead_calculation": overhead_calc,
                "overhead_calculation_json": overhead_calc_json,
                "tc_change_url_zero": tc_change_url_zero,
            }
        )
        return super().change_view(request, object_id, form_url, extra_context=extra)


# @admin.register(Group)
# class GroupAdmin(admin.ModelAdmin):
#     list_display = ("id", "name", "estimate", "parent", "order")
#     list_filter = ("estimate",)
#     search_fields = ("name",)
#     raw_id_fields = ("estimate", "parent")
#     inlines = (GroupTechnicalCardLinkInline,)

#     # Немного удобства: группируем по смете и порядку
#     def get_queryset(self, request):
#         qs = super().get_queryset(request)
#         return qs.select_related("estimate", "parent")
