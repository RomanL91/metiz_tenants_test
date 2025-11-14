"""
Админ-панель для модуля «Сметы» (app_outlay).
"""

import json
import os

from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from app_estimate_imports.services.schema_service import SchemaService as _SS
from app_outlay.estimate_mapping_utils import TechnicalCardDetector, UnitNormalizer
from app_outlay.forms import GroupFormSet, LinkFormSet
from app_outlay.models import (
    Estimate,
    EstimateOverheadCostLink,
    Group,
    GroupTechnicalCardLink,
)
from app_outlay.utils import ExcelSheetReader
from app_outlay.views.estimate_calc_view.utils_calc import DEFAULT_ORDER
from app_overhead_costs.models import OverheadCostContainer as _OHC
from app_technical_cards.models import TechnicalCard as _TC

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
    "TOTAL_PRICE_WITHOUT_VAT": "ИТОГО БЕЗ НДС",
    "VAT_AMOUNT": "НДС",
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
        "name",
        "source_file",
        "currency",
    )
    search_fields = ("name",)
    readonly_fields = (
        "source_file",
        "source_sheet_index",
        "settings_data",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _groups_count=Count("groups", distinct=False),
            _tc_links_count=Count("groups__techcard_links", distinct=True),
            _overhead_count=Count("overhead_cost_links", distinct=True),
        )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            # Страница детального анализа
            path(
                "<path:object_id>/analysis/",
                self.admin_site.admin_view(self.analysis_view),
                name="estimate_analysis",
            ),
        ]
        return custom + urls

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
            self.admin_site.each_context(request),
            title=f"Анализ сметы: {est.name}",
            estimate=est,
            has_data=est.groups.exists(),
        )

        return TemplateResponse(
            request, "admin/app_outlay/estimate_analysis.html", context
        )

    # ---------- ПРЕДСТАВЛЕНИЯ ----------

    def render_change_form(
        self, request, context, add=False, change=False, form_url="", obj=None
    ):
        """Переопределение формы редактирования сметы."""
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

        # POST: валидация и сохранение формсетов
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

            if gfs.is_valid() and lfs.is_valid() and ofs.is_valid():
                with transaction.atomic():
                    gfs.save()
                    lfs.save()

                    for form in ofs.forms:
                        if form.cleaned_data and not form.cleaned_data.get(
                            "DELETE", False
                        ):
                            instance = form.save(commit=False)
                            instance.estimate = obj
                            instance.save()

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
                        "links": lforms_by_gid.get(g.pk, []),
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
                "overhead_formset": ofs,
                "overhead_links": list(overhead_qs),
                "list_url": reverse(
                    f"admin:{Estimate._meta.app_label}_{Estimate._meta.model_name}_changelist"
                ),
            }
        )
        return super().render_change_form(request, context, add, change, form_url, obj)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """Переопределение view для добавления превью сопоставления ТК."""
        extra = dict(extra_context or {})
        est = self.get_object(request, object_id)

        # Контекст по умолчанию
        table_sections: list[dict] = []
        optional_cols: list[dict] = []
        role_titles = ROLE_TITLES
        existing_mappings = {}

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
            unit_allow_set = set()
            require_qty = False
            col_roles: list[str] = []

            # Создаём normalizer для переиспользования
            unit_normalizer = UnitNormalizer()

            try:
                col_roles, unit_allow_set, require_qty = _SS().read_sheet_schema(
                    markup, sheet_i
                )
                # Нормализуем через UnitNormalizer.normalize_set()
                unit_allow_set = unit_normalizer.normalize_set(unit_allow_set or set())
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
                    # Нормализуем каждую единицу через normalizer
                    n = unit_normalizer.normalize(part)
                    if n:
                        unit_allow_set.add(n)
                require_qty = bool(sch.get("require_qty"))

            # --- 2) Загружаем ПОЛНЫЙ лист Excel через новый ООП reader
            xlsx_path = getattr(est.source_file.file, "path", None) or (
                (pr.data or {}).get("file") or {}
            ).get("path")

            if xlsx_path:
                # Используем ExcelSheetReader
                reader = ExcelSheetReader(
                    path=xlsx_path, sheet_index=sheet_i, use_cache=True, cache_ttl=600
                )
                rows_full = reader.read_all_rows()
            else:
                rows_full = []

            # --- 3) Детектируем ТК через новый детектор
            detector = TechnicalCardDetector(
                col_roles=col_roles,
                unit_allow_set=unit_allow_set,
                require_qty=require_qty,
                optional_role_ids=OPTIONAL_ROLE_IDS,
                unit_normalizer=unit_normalizer,  # Передаём тот же normalizer
            )

            tcs = detector.detect_from_rows(rows_full)

            # --- 4) Построение дерева групп
            tree, loose = detector.build_tree_with_groups(
                tcs=tcs, annotation=markup.annotation or {}, sheet_index=sheet_i
            )

            # --- 5) Собираем кандидатов для таблицы UI
            allowed_rows = {tc["row_index"] for tc in tcs}
            candidates_all = detector.collect_candidates_with_optional_columns(
                rows_full
            )
            candidates_filtered = [
                it for it in candidates_all if it["row_index"] in allowed_rows
            ]

            # --- 6) Опциональные колонки для UI
            present_optional = [rid for rid in OPTIONAL_ROLE_IDS if rid in col_roles]
            optional_cols = [
                {"id": rid, "title": role_titles.get(rid, rid)}
                for rid in present_optional
            ]

            # КРИТИЧНО: для JS-расчетов всегда передаём ПОЛНЫЙ порядок (DEFAULT_ORDER)
            # чтобы итоговое табло работало независимо от разметки колонок
            full_calc_order = list(DEFAULT_ORDER)

            for it in candidates_filtered:
                raw = it.get("excel_optional") or {}
                # Сохраняем и значения, и ID колонок
                it["opt_values"] = [
                    {"value": raw.get(col["id"], ""), "rid": col["id"]}
                    for col in optional_cols
                ]

            # --- 7) Формирование секций для UI
            cand_by_row = {it["row_index"]: it for it in candidates_filtered}
            table_sections = []

            if tree:

                def _flatten(node: dict, parent_path: str | None = None):
                    """Рекурсивное выравнивание дерева в секции."""
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

                for root in tree:
                    _flatten(root)

                # Loose items
                loose_items = []
                for tc in loose:
                    ci = cand_by_row.get(tc["row_index"])
                    if ci:
                        loose_items.append(ci)

                if loose_items:
                    table_sections.append(
                        {"path": "Без группы", "color": "#f0f4f8", "items": loose_items}
                    )
            else:
                # Нет групп — всё в одной секции
                if candidates_filtered:
                    table_sections = [
                        {
                            "path": "Без группы",
                            "color": "#f0f4f8",
                            "items": candidates_filtered,
                        }
                    ]

            # --- 8) Загружаем существующие сопоставления из БД
            if est:
                links_qs = GroupTechnicalCardLink.objects.filter(
                    group__estimate=est
                ).select_related(
                    "group", "technical_card_version", "technical_card_version__card"
                )

                for link in links_qs:
                    if link.source_row_index:
                        existing_mappings[link.source_row_index] = {
                            # всегда кладём ID карточки
                            "tc_id": link.technical_card_version.card_id,
                            # Legacy для совместимости (если где-то ещё используется)
                            "tc_version_id": link.technical_card_version_id,
                            "tc_name": link.technical_card_version.card.name,
                            "quantity": float(link.quantity),
                        }

        # URL для изменения ТК
        tc_change_url_zero = reverse(
            f"admin:{_TC._meta.app_label}_{_TC._meta.model_name}_change",
            args=[0],
        )
        # URL для изменения контейнера НР
        ohc_change_url_zero = reverse(
            f"admin:{_OHC._meta.app_label}_{_OHC._meta.model_name}_change",
            args=[0],
        )

        # Финальный контекст
        extra.update(
            {
                "table_sections": table_sections,
                "optional_cols": optional_cols,
                # Передаём ПОЛНЫЙ порядок для корректной работы итогового табло
                "calc_order_json": json.dumps(full_calc_order, ensure_ascii=False),
                # Для UI таблицы — только размеченные колонки
                "optional_cols_ids": [c["id"] for c in optional_cols],
                "role_titles": role_titles,
                "table_colspan": 4 + len(optional_cols),
                "existing_mappings_json": json.dumps(
                    existing_mappings, ensure_ascii=False
                ),
                "tc_change_url_zero": tc_change_url_zero,
                "ohc_change_url_zero": ohc_change_url_zero,
            }
        )

        return super().change_view(request, object_id, form_url, extra_context=extra)
