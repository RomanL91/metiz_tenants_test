from django.contrib import admin, messages
from django.urls import reverse, path
from django.http import HttpResponseRedirect, JsonResponse

from app_technical_cards.models import TechnicalCard

from app_outlay.models import Estimate, Group, GroupTechnicalCardLink
from app_outlay.forms import GroupFormSet, LinkFormSet

# ---------- INLINES ----------


class GroupTechnicalCardLinkInline(admin.TabularInline):
    model = GroupTechnicalCardLink
    extra = 0
    ordering = ("order", "id")
    raw_id_fields = ("technical_card_version",)
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

    # — отрисовка вычисляемых полей «как в смете»
    def unit_display(self, obj):
        return obj.unit or ""

    unit_display.short_description = "Ед. ТК"

    def unit_cost_materials_display(self, obj):
        v = obj.unit_cost_materials
        return "—" if v in (None, "") else f"{v:.2f}"

    unit_cost_materials_display.short_description = "Цена МАТ/ед"

    def unit_cost_works_display(self, obj):
        v = obj.unit_cost_works
        return "—" if v in (None, "") else f"{v:.2f}"

    unit_cost_works_display.short_description = "Цена РАБ/ед"

    def unit_cost_total_display(self, obj):
        v = obj.unit_cost_total
        return "—" if v in (None, "") else f"{v:.2f}"

    unit_cost_total_display.short_description = "Итого / ед (ТК)"

    def total_cost_materials_display(self, obj):
        v = obj.total_cost_materials
        return "—" if v in (None, "") else f"{v:.2f}"

    total_cost_materials_display.short_description = "МАТ × кол-во"

    def total_cost_works_display(self, obj):
        v = obj.total_cost_works
        return "—" if v in (None, "") else f"{v:.2f}"

    total_cost_works_display.short_description = "РАБ × кол-во"

    def total_cost_display(self, obj):
        v = obj.total_cost
        return "—" if v in (None, "") else f"{v:.2f}"

    total_cost_display.short_description = "Итого (МАТ+РАБ) × кол-во"


# ---------- АДМИНКИ ----------
from openpyxl import load_workbook

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
    # change_form_template = "admin/app_outlay/estimate_tree.html"
    change_form_template = "admin/app_outlay/estimate_change.html"
    list_display = (
        "id",
        "name",
        "currency",
        "groups_count",
        "tc_links_count",
    )
    search_fields = ("name",)

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
        ]
        return custom + urls

    def tc_autocomplete(self, request, *args, **kwargs):
        """Простой автокомплит по ТК."""
        q = (request.GET.get("q") or "").strip()
        qs = (
            TechnicalCard.objects.all()
        )  # если нужно выбирать версию — поменяй на TechnicalCardVersion
        if q:
            qs = qs.filter(name__icontains=q)
        data = [{"id": obj.pk, "text": obj.name} for obj in qs[:20]]
        return JsonResponse({"results": data})

    def groups_count(self, obj):
        return obj.groups.count()

    groups_count.short_description = "Групп"

    def tc_links_count(self, obj):
        # Быстрый подсчёт через related name
        return GroupTechnicalCardLink.objects.filter(group__estimate=obj).count()

    tc_links_count.short_description = "ТК в смете"

    def render_change_form(
        self, request, context, add=False, change=False, form_url="", obj=None
    ):
        # на стандартный add оставляем дефолтное поведение
        if add or obj is None:
            return super().render_change_form(
                request, context, add, change, form_url, obj
            )

        # источники данных
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
        if not group_qs.exists():
            Group.objects.get_or_create(
                estimate=obj,
                parent=None,
                defaults={"name": "Общий раздел", "order": 0},
            )
            group_qs = Group.objects.filter(estimate=obj).order_by(
                "parent_id", "order", "id"
            )

        # POST: валидируем и сохраняем оба формсета
        if request.method == "POST":
            gfs = GroupFormSet(request.POST, queryset=group_qs, prefix="grp")
            lfs = LinkFormSet(request.POST, queryset=link_qs, prefix="lnk")
            if gfs.is_valid() and lfs.is_valid():
                gfs.save()
                lfs.save()
                self.message_user(
                    request, "Изменения сохранены", level=messages.SUCCESS
                )
                return HttpResponseRedirect(request.path)
            else:
                self.message_user(
                    request, "Исправьте ошибки в форме", level=messages.ERROR
                )
        else:
            gfs = GroupFormSet(queryset=group_qs, prefix="grp")
            lfs = LinkFormSet(queryset=link_qs, prefix="lnk")

        # строим дерево групп (parent → children), и маппим формы по pk
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

        context.update(
            {
                "title": f"Смета: {obj.name}",
                "tree": tree,
                "group_formset": gfs,
                "link_formset": lfs,
                "list_url": reverse(
                    f"admin:{Estimate._meta.app_label}_{Estimate._meta.model_name}_changelist"
                ),
            }
        )
        return super().render_change_form(request, context, add, change, form_url, obj)

    # def change_view(self, request, object_id, form_url="", extra_context=None):
    #     # TODO бля
    #     from .helpers import (
    #         _load_groups_from_annotation,
    #         _read_sheet_schema,
    #         _detect_tc_rows,
    #         _assign_tc_to_deepest_group,
    #     )

    #     extra_context = extra_context or {}
    #     est = self.get_object(request, object_id)
    #     preview = {"groups": [], "loose": [], "ready": False}

    #     if (
    #         est
    #         and est.source_file
    #         and hasattr(est.source_file, "parse_result")
    #         and hasattr(est.source_file, "markup")
    #     ):
    #         pr = est.source_file.parse_result
    #         markup = est.source_file.markup
    #         sheet_i = est.source_sheet_index or 0

    #         groups = _load_groups_from_annotation(markup.annotation or {}, sheet_i)
    #         col_roles, unit_set, require_qty = _read_sheet_schema(markup, sheet_i)
    #         tcs = _detect_tc_rows(
    #             pr.data or {}, sheet_i, col_roles, unit_set, require_qty
    #         )
    #         tree, loose = _assign_tc_to_deepest_group(groups, tcs)

    #         # если групп нет — создаём «Без группы» и кидаем туда все ТК
    #         if not tree and not groups:
    #             tree = [
    #                 {
    #                     "uid": "_virtual",
    #                     "name": "Без группы",
    #                     "color": "#eceff1",
    #                     "tcs": tcs,
    #                     "children": [],
    #                 }
    #             ]
    #             loose = []

    #         preview = {"groups": tree, "loose": loose, "ready": True}

    #     extra_context["tc_preview"] = preview
    #     extra_context["tc_autocomplete_url"] = "outlay_tc_autocomplete"
    #     return super().change_view(
    #         request, object_id, form_url, extra_context=extra_context
    #     )

    # def change_view(self, request, object_id, form_url="", extra_context=None):
    #     import json
    #     from django.urls import reverse
    #     from .helpers import (
    #         _load_groups_from_annotation,
    #         _read_sheet_schema,
    #         _detect_tc_rows,
    #         _assign_tc_to_deepest_group,
    #         ROLE_TITLES,
    #         OPTIONAL_ROLE_IDS,
    #         _collect_excel_candidates,
    #         load_sheet_rows_full,
    #     )

    #     extra = dict(extra_context or {})
    #     est = self.get_object(request, object_id)

    #     preview = {"groups": [], "loose": [], "ready": False}
    #     excel_candidates = []
    #     optional_cols = []
    #     role_titles = ROLE_TITLES

    #     if (
    #         est
    #         and est.source_file_id
    #         and hasattr(est.source_file, "parse_result")
    #         and hasattr(est.source_file, "markup")
    #     ):
    #         pr = est.source_file.parse_result
    #         markup = est.source_file.markup
    #         sheet_i = est.source_sheet_index or 0

    #         groups = _load_groups_from_annotation(markup.annotation or {}, sheet_i)

    #         # глубина групп
    #         by_id = {g["uid"]: g for g in groups}

    #         def _depth(uid):
    #             d = 0
    #             cur = by_id.get(uid)
    #             while cur and cur.get("parent_uid"):
    #                 d += 1
    #                 cur = by_id.get(cur.get("parent_uid"))
    #             return d

    #         for g in groups:
    #             g["_depth"] = _depth(g["uid"])

    #         col_roles, unit_set, require_qty = _read_sheet_schema(markup, sheet_i)
    #         xlsx_path = getattr(est.source_file.file, "path", None) or (
    #             pr.data.get("file") or {}
    #         ).get("path")
    #         full_rows = []
    #         if xlsx_path:
    #             try:
    #                 full_rows = load_sheet_rows_full(xlsx_path, sheet_index=sheet_i)
    #             except Exception:
    #                 full_rows = []
    #         tcs = _detect_tc_rows(
    #             pr.data or {}, sheet_i, col_roles, unit_set, require_qty, rows=full_rows
    #         )
    #         tree, loose = _assign_tc_to_deepest_group(groups, tcs)
    #         if not tree and not groups:
    #             tree = [
    #                 {
    #                     "uid": "_virtual",
    #                     "name": "Без группы",
    #                     "color": "#eceff1",
    #                     "tcs": tcs,
    #                     "children": [],
    #                 }
    #             ]
    #             loose = []
    #         preview = {"groups": tree, "loose": loose, "ready": True}

    #         # ВСЕ строки листа
    #         xlsx_path = getattr(est.source_file.file, "path", None) or (
    #             pr.data.get("file") or {}
    #         ).get("path")
    #         excel_candidates = _collect_excel_candidates(
    #             pr, col_roles, sheet_i, xlsx_path=xlsx_path, load_full=True
    #         )

    #         # подсветка: ищем самую глубокую накрывающую группу
    #         def _owner_group(row_index: int):
    #             cov = []
    #             for g in groups:
    #                 for s, e in g.get("rows") or []:
    #                     if s <= row_index <= e:
    #                         cov.append(g)
    #                         break
    #             if not cov:
    #                 return None
    #             cov.sort(key=lambda x: x["_depth"])
    #             return cov[-1]

    #         for it in excel_candidates:
    #             gi = _owner_group(it.get("row_index") or 0)
    #             it["group_color"] = (gi or {}).get("color")
    #             it["group_name"] = (gi or {}).get("name")

    #         present_optional = [rid for rid in OPTIONAL_ROLE_IDS if rid in col_roles]
    #         optional_cols = [
    #             {"id": rid, "title": role_titles.get(rid, rid)}
    #             for rid in present_optional
    #         ]
    #         for it in excel_candidates:
    #             raw = it.get("excel_optional") or {}
    #             it["opt_values"] = [raw.get(rid) for rid in present_optional]

    #     extra.update(
    #         {
    #             "tc_preview": preview,
    #             "excel_candidates": excel_candidates,
    #             "optional_cols": optional_cols,
    #             "optional_cols_json": json.dumps(optional_cols, ensure_ascii=False),
    #             "role_titles": role_titles,
    #             "tc_autocomplete_url": reverse("admin:outlay_tc_autocomplete"),
    #         }
    #     )
    #     return super().change_view(request, object_id, form_url, extra_context=extra)

    def api_calc(self, request, object_id: str):
        """Возвращает «системные» стоимости для выбранной ТК и qty.
        Пока заглушка: вернёт нули, если нет цен/норм в модели.
        Позже подключим полноценный сервис ценообразования.
        """
        try:
            tc_id = int(request.GET.get("tc") or 0)
            qty = float(request.GET.get("qty") or 0)
        except Exception:
            return JsonResponse({"ok": False, "error": "bad_params"}, status=400)

        # TODO: заменить на реальный расчёт.
        # пример целевых полей (совпадает с ролями):
        calc = {
            "UNIT_PRICE_OF_MATERIAL": 0.0,
            "UNIT_PRICE_OF_WORK": 0.0,
            "UNIT_PRICE_OF_MATERIALS_AND_WORKS": 0.0,
            "PRICE_FOR_ALL_MATERIAL": 0.0,
            "PRICE_FOR_ALL_WORK": 0.0,
            "TOTAL_PRICE": 0.0,
        }
        # если уже есть в системе цены/нормы — здесь их агрегируем:
        # calc["UNIT_PRICE_OF_MATERIAL"] = ...
        # calc["UNIT_PRICE_OF_WORK"] = ...
        # calc["UNIT_PRICE_OF_MATERIALS_AND_WORKS"] = calc["UNIT_PRICE_OF_MATERIAL"] + calc["UNIT_PRICE_OF_WORK"]
        # calc["PRICE_FOR_ALL_MATERIAL"] = calc["UNIT_PRICE_OF_MATERIAL"] * qty
        # calc["PRICE_FOR_ALL_WORK"] = calc["UNIT_PRICE_OF_WORK"] * qty
        # calc["TOTAL_PRICE"] = calc["UNIT_PRICE_OF_MATERIALS_AND_WORKS"] * qty

        return JsonResponse({"ok": True, "calc": calc})

        # ---------- ВСПОМОГАТЕЛЬНОЕ: читаем полный лист Excel ----------

    def _load_full_sheet_rows(self, xlsx_path: str, sheet_index: int) -> list[dict]:
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
        for r in ws.iter_rows(
            min_row=1, max_row=min(200, ws.max_row), values_only=True
        ):
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

    # ---------- change_view: используем ПОЛНЫЕ строки и красим группы ----------
    # def change_view(self, request, object_id, form_url="", extra_context=None):
    #     import json

    #     extra = dict(extra_context or {})
    #     est = self.get_object(request, object_id)

    #     preview = {"groups": [], "loose": [], "ready": False}
    #     excel_candidates = []
    #     optional_cols = []  # [{id, title}]
    #     role_titles = ROLE_TITLES

    #     if (
    #         est
    #         and est.source_file_id
    #         and hasattr(est.source_file, "parse_result")
    #         and hasattr(est.source_file, "markup")
    #     ):
    #         pr = est.source_file.parse_result
    #         markup = est.source_file.markup
    #         sheet_i = est.source_sheet_index or 0

    #         # 1) роли/юниты/обязательность qty
    #         from app_estimate_imports.services.schema_service import (
    #             SchemaService as _SS,
    #         )  # если есть сервис

    #         try:
    #             col_roles, unit_set, require_qty = _SS().read_sheet_schema(
    #                 markup, sheet_i
    #             )
    #         except Exception:
    #             # фолбэк: без сервиса — пустые настройки
    #             col_roles, unit_set, require_qty = (
    #                 (markup.annotation or {})
    #                 .get("schema", {})
    #                 .get("sheets", {})
    #                 .get(str(sheet_i), {})
    #                 .get("col_roles")
    #                 or [],
    #                 set(),
    #                 False,
    #             )

    #         # 2) полный лист Excel
    #         xlsx_path = getattr(est.source_file.file, "path", None) or (
    #             pr.data.get("file") or {}
    #         ).get("path")
    #         if xlsx_path:
    #             rows_full = self._load_full_sheet_rows(xlsx_path, sheet_i)
    #         else:
    #             rows_full = pr.data.get("sheets", [{}])[sheet_i].get("rows") or []

    #         # 3) кандидаты ТК + группы по annotation
    #         tcs = self._detect_tc_rows_from_rows(
    #             rows_full, col_roles, unit_set, require_qty
    #         )
    #         groups = self._load_groups_from_annotation(markup.annotation or {}, sheet_i)
    #         tree, loose = self._assign_tc_to_deepest_group(groups, tcs)

    #         if not tree and not groups:
    #             # виртуальная «Без группы»
    #             tree = [
    #                 {
    #                     "uid": "_virtual",
    #                     "name": "Без группы",
    #                     "color": "#f0f4f8",
    #                     "tcs": tcs,
    #                     "children": [],
    #                 }
    #             ]
    #             loose = []

    #         preview = {"groups": tree, "loose": loose, "ready": True}

    #         # 4) таблица сопоставления по ПОЛНЫМ строкам
    #         excel_candidates = self._collect_excel_candidates_from_rows(
    #             rows_full, col_roles
    #         )
    #         present_optional = [rid for rid in OPTIONAL_ROLE_IDS if rid in col_roles]
    #         optional_cols = [
    #             {"id": rid, "title": role_titles.get(rid, rid)}
    #             for rid in present_optional
    #         ]

    #         present_optional = [rid for rid in OPTIONAL_ROLE_IDS if rid in col_roles]
    #         optional_cols = [
    #             {"id": rid, "title": role_titles.get(rid, rid)}
    #             for rid in present_optional
    #         ]
    #         excel_all = self._collect_excel_candidates_from_rows(rows_full, col_roles)
    #         # оставляем только строки, которые мы признали ТК
    #         allowed_rows = {tc["row_index"] for tc in tcs}
    #         excel_candidates = [
    #             it for it in excel_all if it["row_index"] in allowed_rows
    #         ]

    #         # подготовим значения опциональных полей в порядке optional_cols
    #         for it in excel_candidates:
    #             raw = it.get("excel_optional") or {}
    #             it["opt_values"] = [raw.get(r["id"]) for r in optional_cols]

    #         # секции для таблицы по дереву групп (включая подгруппы)
    #         cand_by_row = {it["row_index"]: it for it in excel_candidates}
    #         table_sections: list[dict] = []

    #         def _flatten_group(node: dict, parent_path: str | None = None):
    #             path = node.get("name") or "Группа"
    #             path = path if parent_path is None else f"{parent_path} / {path}"
    #             items = []
    #             for tc in node.get("tcs") or []:
    #                 ci = cand_by_row.get(tc["row_index"])
    #                 if ci:
    #                     items.append(ci)
    #             table_sections.append(
    #                 {
    #                     "path": path,
    #                     "color": node.get("color") or "#eef",
    #                     "items": items,
    #                 }
    #             )
    #             for ch in node.get("children") or []:
    #                 _flatten_group(ch, path)

    #         for root in tree or []:
    #             _flatten_group(root)

    #         # «Без группы»
    #         loose_items = []
    #         for tc in loose or []:
    #             ci = cand_by_row.get(tc["row_index"])
    #             if ci:
    #                 loose_items.append(ci)
    #         if loose_items:
    #             table_sections.append(
    #                 {
    #                     "path": "Без группы",
    #                     "color": "#f0f4f8",
    #                     "items": loose_items,
    #                 }
    #             )

    #     extra.update(
    #         {
    #             "tc_preview": preview,
    #             "excel_candidates": excel_candidates,
    #             "optional_cols": optional_cols,
    #             "optional_cols_json": json.dumps(optional_cols, ensure_ascii=False),
    #             "role_titles": role_titles,
    #             "tc_autocomplete_url": reverse("admin:outlay_tc_autocomplete"),
    #             "table_sections": table_sections,
    #             "calc_order_json": json.dumps(
    #                 [c["id"] for c in optional_cols], ensure_ascii=False
    #             ),
    #             "table_colspan": 4 + len(optional_cols),
    #         }
    #     )
    #     return super().change_view(request, object_id, form_url, extra_context=extra)
    def change_view(self, request, object_id, form_url="", extra_context=None):
        import json
        from django.urls import reverse

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
                rows_full = self._load_full_sheet_rows(xlsx_path, sheet_i)
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
            }
        )
        return super().change_view(request, object_id, form_url, extra_context=extra)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "estimate", "parent", "order")
    list_filter = ("estimate",)
    search_fields = ("name",)
    raw_id_fields = ("estimate", "parent")
    inlines = (GroupTechnicalCardLinkInline,)

    # Немного удобства: группируем по смете и порядку
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("estimate", "parent")
