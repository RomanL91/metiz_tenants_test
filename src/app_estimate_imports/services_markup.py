from __future__ import annotations

from typing import Iterable
from django.db import transaction

import hashlib, re
from typing import Iterable

from .models import ParseMarkup
from .utils_markup import ensure_uids_in_tree

ALLOWED_LABELS = {"TECH_CARD", "WORK", "MATERIAL", "GROUP"}


def ensure_markup_exists(file_obj) -> ParseMarkup:
    """
    Гарантирует наличие ParseMarkup и uid'ов в ParseResult.data.
    """
    pr = getattr(file_obj, "parse_result", None)
    if not pr:
        raise ValueError("Нет ParseResult для файла")

    # Проставим uid всем узлам
    pr.data = ensure_uids_in_tree(pr.data)
    pr.save(update_fields=["data"])

    markup = getattr(file_obj, "markup", None)
    if not markup:
        markup = ParseMarkup.objects.create(
            file=file_obj, parse_result=pr, annotation={"labels": {}, "tech_cards": []}
        )
    else:
        ann = markup.annotation or {}
        ann.setdefault("labels", {})
        ann.setdefault("tech_cards", [])
        markup.annotation = ann
        markup.save(update_fields=["annotation"])
    return markup


def list_nodes(parse_result) -> list[dict]:
    """
    Плоский список узлов дерева: [{uid, title, path}]
    path — собираем из titles родителей (для читаемости).
    """
    nodes: list[dict] = []

    def walk(node: dict, parents: list[str]):
        uid = node.get("uid")
        title = node.get("title") or ""
        path = " / ".join([*parents, title]) if title else " / ".join(parents)
        if uid:
            nodes.append({"uid": uid, "title": title, "path": path})
        for ch in node.get("children") or []:
            walk(ch, [*parents, title] if title else parents)

    for sheet in parse_result.data.get("sheets") or []:
        for b in sheet.get("blocks") or []:
            walk(b, [sheet.get("name") or "Лист"])
    return nodes


@transaction.atomic
def set_label(file_obj, uid: str, label: str, title: str | None = None) -> None:
    if label not in ALLOWED_LABELS:
        raise ValueError(f"Недопустимая метка: {label}")
    markup = ensure_markup_exists(file_obj)
    ann = markup.annotation
    ann["labels"][uid] = label
    if title:
        ann.setdefault("names", {})[uid] = title  # ← словарь имён для uid
    markup.annotation = ann
    markup.save(update_fields=["annotation"])


@transaction.atomic
def set_tc_members(
    file_obj, tc_uid: str, works: Iterable[str], materials: Iterable[str]
) -> None:
    """
    Задаёт состав ТК: список uid'ов работ и материалов.
    Если записи для tc_uid ещё нет — создаётся.
    """
    markup = ensure_markup_exists(file_obj)
    ann = markup.annotation
    tcs: list[dict] = ann.get("tech_cards", [])

    # ищем существующую запись
    entry = next((x for x in tcs if x.get("uid") == tc_uid), None)
    if not entry:
        entry = {"uid": tc_uid, "works": [], "materials": []}
        tcs.append(entry)

    entry["works"] = list(dict.fromkeys(works or []))  # dedup сохраним порядок
    entry["materials"] = list(dict.fromkeys(materials or []))

    ann["tech_cards"] = tcs
    markup.annotation = ann
    markup.save(update_fields=["annotation"])


def build_markup_skeleton(parse_result) -> dict:
    """
    Строит черновик:
    - labels: все найденные uid -> "GROUP" (можно править руками в админке)
    - tech_cards: []
    """
    data = ensure_uids_in_tree(parse_result.data)
    labels: dict[str, str] = {}

    def collect(blocks: list):
        for b in blocks:
            uid = b.get("uid")
            if uid:
                labels[uid] = "GROUP"
            ch = b.get("children") or []
            if ch:
                collect(ch)

    for sheet in data.get("sheets") or []:
        collect(sheet.get("blocks") or [])

    return {"labels": labels, "tech_cards": []}


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def build_annotation_from_grid(
    parse_result,
    col_roles: list[str],
    *,
    sheet_index: int = 0,
    existing: dict | None = None,
) -> dict:
    """
    sheet_index — с какого листа брать строки.
    Остальное — как раньше, sticky TC по пути GROUP-*.
    """
    data = parse_result.data or {}
    sheets = data.get("sheets") or []
    sheet = (
        sheets[sheet_index]
        if 0 <= sheet_index < len(sheets)
        else (sheets[0] if sheets else {"rows": []})
    )
    rows = sheet.get("rows") or []

    labels = (existing or {}).get("labels", {}).copy()
    names = (existing or {}).get("names", {}).copy()
    tech_list: list[dict] = (existing or {}).get("tech_cards", []).copy()

    def upsert_tc_entry(tc_uid: str) -> dict:
        for e in tech_list:
            if e.get("uid") == tc_uid:
                return e
        e = {"uid": tc_uid, "works": [], "materials": []}
        tech_list.append(e)
        return e

    group_cols = [
        i
        for i, r in enumerate(col_roles)
        if isinstance(r, str) and r.startswith("GROUP-")
    ]
    tc_cols = [i for i, r in enumerate(col_roles) if r == "TECH_CARD"]
    work_cols = [i for i, r in enumerate(col_roles) if r == "WORK"]
    mat_cols = [i for i, r in enumerate(col_roles) if r == "MATERIAL"]
    # unit/qty можно позже прикрутить в атрибуты

    last_tc_by_group_path: dict[tuple[str, ...], str] = {}

    for r in rows:
        cells = r.get("cells") or []

        g_path_vals: list[str] = []
        for gi in sorted(group_cols):
            v = (cells[gi] or "").strip() if gi < len(cells) else ""
            if v:
                g_path_vals.append(v)
        g_path = tuple(g_path_vals)

        # зарегистрируем групповые узлы
        for depth, val in enumerate(g_path_vals, start=1):
            nid = f"s{sheet_index}-G{depth}-{_short_hash(val)}"
            labels[nid] = "GROUP"
            names[nid] = val

        tc_uids: list[str] = []
        for ci in tc_cols:
            v = (cells[ci] or "").strip() if ci < len(cells) else ""
            if not v:
                continue
            nid = f"s{sheet_index}-TC-{ci}-{_short_hash(v)}"
            labels[nid] = "TECH_CARD"
            names[nid] = v
            tc_uids.append(nid)
            last_tc_by_group_path[g_path] = nid

        works_uids: list[str] = []
        for ci in work_cols:
            v = (cells[ci] or "").strip() if ci < len(cells) else ""
            if not v:
                continue
            nid = f"s{sheet_index}-W-{ci}-{_short_hash(v)}"
            labels[nid] = "WORK"
            names[nid] = v
            works_uids.append(nid)

        mats_uids: list[str] = []
        for ci in mat_cols:
            v = (cells[ci] or "").strip() if ci < len(cells) else ""
            if not v:
                continue
            nid = f"s{sheet_index}-M-{ci}-{_short_hash(v)}"
            labels[nid] = "MATERIAL"
            names[nid] = v
            mats_uids.append(nid)

        if (works_uids or mats_uids) and not tc_uids:
            sticky = last_tc_by_group_path.get(g_path)
            if sticky:
                tc_uids = [sticky]

        for tc in tc_uids:
            e = upsert_tc_entry(tc)
            for w in works_uids:
                if w not in e["works"]:
                    e["works"].append(w)
            for m in mats_uids:
                if m not in e["materials"]:
                    e["materials"].append(m)

    annotation = (existing or {}).copy()
    annotation["labels"] = labels
    annotation["names"] = names
    annotation["tech_cards"] = tech_list
    # схему по листу сохраняем в admin.api_extract_from_grid
    return annotation
