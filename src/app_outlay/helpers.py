# app_outlay/helpers.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Iterable, Optional

# ---- роли и заголовки ----
ROLE_DEFS_RAW = [
    ("NONE", "—", None, False),
    ("NAME_OF_WORK", "НАИМЕНОВАНИЕ РАБОТ/ТК", "#E3F2FD", True),
    ("UNIT", "ЕД. ИЗМ.", "#FFF8E1", True),
    ("QTY", "КОЛ-ВО", "#E8F5E9", True),
    ("UNIT_PRICE_OF_MATERIAL", "ЦЕНА МАТ/ЕД", "#F3E5F5", False),
    ("UNIT_PRICE_OF_WORK", "ЦЕНА РАБОТЫ/ЕД", "#EDE7F6", False),
    ("UNIT_PRICE_OF_MATERIALS_AND_WORKS", "ЦЕНА МАТ+РАБ/ЕД", "#E1F5FE", False),
    ("PRICE_FOR_ALL_MATERIAL", "ИТОГО МАТЕРИАЛ", "#FBE9E7", False),
    ("PRICE_FOR_ALL_WORK", "ИТОГО РАБОТА", "#FFF3E0", False),
    ("TOTAL_PRICE", "ОБЩАЯ ЦЕНА", "#FFEBEE", False),
]
ROLE_TITLES = {r[0]: r[1] for r in ROLE_DEFS_RAW}
OPTIONAL_ROLE_IDS = [r[0] for r in ROLE_DEFS_RAW if not r[3] and r[0] != "NONE"]


# ---- утилиты ----
def _idxs(col_roles: List[str], role_id: str) -> List[int]:
    """Номера колонок, помеченных заданной ролью."""
    return [i for i, rid in enumerate(col_roles or []) if rid == role_id]


def _cell(row: List[Any], col: int) -> Any:
    return row[col] if 0 <= col < len(row) else None


def _to_text(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s


def _parse_number(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            f = float(v)
        except Exception:
            return None
        return f
    s = str(v).strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def _normalize_unit(u: str) -> str:
    s = (u or "").lower().strip()
    s = (
        s.replace("\u00b2", "2")
        .replace("\u00b3", "3")
        .replace("^2", "2")
        .replace("^3", "3")
    )
    compact = "".join(ch for ch in s if ch not in " .,")
    # самые частые нормализации
    if compact in {"м2", "квм", "мкв"} or "квадратн" in compact:
        return "м2"
    if compact in {"м3", "кубм", "мкуб"} or "кубическ" in compact:
        return "м3"
    if compact in {"шт", "штук", "штуки", "штука"}:
        return "шт"
    if compact in {"пм", "погм", "погонныйметр", "погонныхметров"}:
        return "пм"
    if compact in {"компл", "комплект", "комплекта", "комплектов"}:
        return "компл"
    return compact


# ---- чтение схемы из markup.annotation ----
def _read_sheet_schema(markup, sheet_index: int) -> tuple[list[str], set[str], bool]:
    ann = getattr(markup, "annotation", {}) or {}
    sdict = ((ann.get("schema") or {}).get("sheets") or {}).get(str(sheet_index)) or {}
    col_roles: List[str] = sdict.get("col_roles") or []
    unit_raw = sdict.get("unit_allow_raw") or ""
    require_qty = bool(sdict.get("require_qty") or False)

    unit_set: set[str] = set()
    for piece in (unit_raw or "").split(","):
        norm = _normalize_unit(piece)
        if norm:
            unit_set.add(norm)
    return col_roles, unit_set, require_qty


# ---- группы из annotation ----
def _load_groups_from_annotation(annotation: dict, sheet_index: int) -> list[dict]:
    sdict = (((annotation or {}).get("schema") or {}).get("sheets") or {}).get(
        str(sheet_index)
    ) or {}
    raw_groups: List[dict] = sdict.get("groups") or []

    by_uid = {
        g["uid"]: {
            "uid": g["uid"],
            "name": g.get("name") or "Группа",
            "rows": g.get("rows") or [],
            "color": g.get("color") or "#eef",
            "parent_uid": g.get("parent_uid"),
            "children": [],
        }
        for g in raw_groups
    }
    roots: list[dict] = []
    for g in by_uid.values():
        p = g.get("parent_uid")
        if p and p in by_uid:
            by_uid[p]["children"].append(g)
        else:
            roots.append(g)
    return roots


# ---- чтение строк листа из parse_result.data ----
def _load_sheet_rows_from_pr(parse_result, sheet_index: int) -> list[list[Any]]:
    data = getattr(parse_result, "data", {}) or {}
    sheets = data.get("sheets") or []
    if (
        not isinstance(sheet_index, int)
        or sheet_index < 0
        or sheet_index >= len(sheets)
    ):
        return []
    rows = sheets[sheet_index].get("rows") or []
    return rows


# ---- сбор «сырых» excel-кандидатов (без фильтрации по условиям) ----
def _collect_excel_candidates(
    parse_result, col_roles: List[str], sheet_index: int
) -> list[dict]:
    rows = _load_sheet_rows_from_pr(parse_result, sheet_index)
    # индексы колонок по ролям
    name_cols = _idxs(col_roles, "NAME_OF_WORK")
    unit_cols = _idxs(col_roles, "UNIT")
    qty_cols = _idxs(col_roles, "QTY")
    opt_cols: dict[str, list[int]] = {
        rid: _idxs(col_roles, rid) for rid in OPTIONAL_ROLE_IDS if rid in col_roles
    }

    out: list[dict] = []
    for r_index, row in enumerate(rows, start=1):
        # берём по ПЕРВОЙ непустой ячейке среди колонок данной роли
        def first(cols: list[int]) -> Any:
            for c in cols:
                v = _cell(row, c)
                if _to_text(v):
                    return v
            return None

        name_raw = first(name_cols)
        unit_raw = first(unit_cols)
        qty_raw = first(qty_cols)

        # собираем исходные значения опциональных ролей (из Excel) в dict
        excel_optional: dict[str, Any] = {}
        for rid, cols in opt_cols.items():
            v = first(cols)
            if v is not None and _to_text(v) != "":
                excel_optional[rid] = v

        out.append(
            {
                "row_index": r_index,
                "name": _to_text(name_raw),
                "unit": _to_text(unit_raw),
                "qty": _parse_number(qty_raw),
                "excel_optional": excel_optional,
            }
        )
    return out


# ---- детект ТК: фильтруем ТОЛЬКО по условиям (и НЕ завязываемся на группы) ----
def _detect_tc_rows(
    parse_result,
    sheet_index: int,
    col_roles: List[str],
    unit_set: set[str],
    require_qty: bool,
) -> list[dict]:
    """
    Возвращает только те строки, которые удовлетворяют правилам:
      - NAME_OF_WORK непусто,
      - UNIT нормализуется и входит в разрешённый набор (если набор не пуст),
      - если require_qty=True, то qty > 0.
    Группы здесь НЕ учитываются — это важно для частичного покрытия.
    """
    raw = _collect_excel_candidates(parse_result, col_roles, sheet_index)

    name_ok = lambda s: bool(_to_text(s))

    def unit_ok(u: str) -> bool:
        norm = _normalize_unit(u)
        return bool(norm) and (not unit_set or norm in unit_set)

    out: list[dict] = []
    for it in raw:
        if not name_ok(it["name"]):
            continue
        if not unit_ok(it["unit"]):
            continue
        if require_qty:
            q = it.get("qty")
            if q is None or q <= 0:
                continue
        out.append(it)
    return out


# ---- вспомогательное: deepest group covering row ----
def _deepest_group_for_row(groups_tree: list[dict], row_index: int) -> Optional[dict]:
    """
    Находит самый глубокий узел, чей диапазон покрывает row_index.
    Если несколько веток накрывают — берём по максимальной глубине.
    """
    best: tuple[int, dict] | None = None

    def covered(node: dict, r: int) -> bool:
        for s, e in node.get("rows") or []:
            if s <= r <= e:
                return True
        return False

    def walk(node: dict, depth: int):
        nonlocal best
        if covered(node, row_index):
            if best is None or depth > best[0]:
                best = (depth, node)
        for ch in node.get("children") or []:
            walk(ch, depth + 1)

    for root in groups_tree or []:
        walk(root, 0)
    return best[1] if best else None


# ---- построение секций для табличного вида, с частичным покрытием ----
def build_table_sections(
    groups_tree: list[dict],
    excel_candidates: list[dict],
) -> list[dict]:
    """
    Складывает кандидатов в секции:
      - если есть группы: по самому глубокому покрывающему узлу;
        кандидаты, которые не накрыл ни один узел, идут в «Без группы».
      - если групп нет вовсе: одна секция «Без группы» со всеми кандидатами.
    """
    if not groups_tree:
        return [
            {
                "path": "Без группы",
                "color": "#f0f4f8",
                "items": list(excel_candidates),
            }
        ]

    # 1) собираем айтемы по узлам (ключ — id(node))
    items_by_node: dict[int, list[dict]] = {}
    ungrouped: list[dict] = []

    for it in excel_candidates:
        row = it["row_index"]
        node = _deepest_group_for_row(groups_tree, row)
        if node is None:
            ungrouped.append(it)
        else:
            items_by_node.setdefault(id(node), []).append(it)

    # 2) обходим дерево в порядке DFS и формируем секции
    sections: list[dict] = []

    def walk(node: dict, parent_path: Optional[str]):
        path = node.get("name") or "Группа"
        path = path if not parent_path else f"{parent_path} / {path}"
        items = items_by_node.get(id(node), [])
        sections.append(
            {
                "path": path,
                "color": node.get("color") or "#eef",
                "items": items,
            }
        )
        for ch in node.get("children") or []:
            walk(ch, path)

    for root in groups_tree:
        walk(root, None)

    if ungrouped:
        sections.append(
            {
                "path": "Без группы",
                "color": "#f0f4f8",
                "items": ungrouped,
            }
        )
    return sections
