import re
from typing import Dict, List, Set, Tuple

from app_estimate_imports.services.base_service import BaseService


class SchemaService(BaseService):
    """Сервис для работы со схемами колонок"""

    UNIT_PATTERNS = {
        "м2": r"(м\^?2|м2|квм|мкв|квадратн\w*метр\w*)",
        "м3": r"(м\^?3|м3|кубм|мкуб|кубическ\w*метр\w*)",
        "шт": r"(шт|штука|штуки|штук)",
        "пм": r"(пм|погм|погонныйметр|погонных\s*метров)",
        "компл": r"(компл|комплект|комплекта|комплектов)",
    }

    def normalize_unit(self, unit: str) -> str:
        """Нормализует единицу измерения"""
        if not unit:
            return ""

        clean = unit.lower().strip()
        clean = clean.replace("\u00b2", "2").replace("\u00b3", "3")
        compact = "".join(ch for ch in clean if ch not in " .,")

        for normalized, pattern in self.UNIT_PATTERNS.items():
            if re.fullmatch(pattern, compact):
                return normalized

        return compact

    def detect_column_roles(self, rows: List[Dict]) -> List[str]:
        """Автоматически определяет роли колонок по заголовкам"""
        max_cols = max((len(r.get("cells") or []) for r in rows), default=0)
        roles = ["NONE"] * max_cols
        header_zone = rows[:8]

        for row in header_zone:
            cells = [(c or "").strip() for c in row.get("cells", [])]
            for col_idx, val in enumerate(cells):
                if col_idx >= max_cols:
                    continue

                low = val.lower()

                if "шифр" in low:
                    roles[col_idx] = "TECH_CARD"
                elif ("наименован" in low and "работ" in low) or low == "наименование":
                    roles[col_idx] = "NAME_OF_WORK"
                elif "ед.изм" in low or "ед. изм" in low:
                    roles[col_idx] = "UNIT"
                elif (
                    "кол-во" in low or "количество" in low or low in {"колво", "кол-во"}
                ):
                    roles[col_idx] = "QTY"
                elif re.fullmatch(r"ур\d+", low):
                    idx = int(re.findall(r"\d+", low)[0])
                    if 1 <= idx <= 6:
                        roles[col_idx] = f"GROUP-{idx}"

        # Если явно не нашли уровни — попробуем 5..8
        if not any(r.startswith("GROUP-") for r in roles) and max_cols >= 9:
            for i, tag in enumerate(
                ["GROUP-1", "GROUP-2", "GROUP-3", "GROUP-4"], start=5
            ):
                if i < max_cols and roles[i] == "NONE":
                    roles[i] = tag

        return roles

    def get_schema_config(
        self, markup, sheet_index: int
    ) -> Tuple[List[str], Set[str], bool]:
        """Получает конфигурацию схемы для листа"""
        annotation = markup.annotation or {}
        schema = annotation.get("schema", {})
        sheets = schema.get("sheets", {})
        sheet_config = sheets.get(str(sheet_index), {})

        col_roles = sheet_config.get("col_roles", [])
        unit_allow_raw = sheet_config.get("unit_allow_raw", "")
        require_qty = bool(sheet_config.get("require_qty", True))

        unit_allow_set = set()
        for unit_str in unit_allow_raw.split(",") if unit_allow_raw else []:
            normalized = self.normalize_unit(unit_str)
            if normalized:
                unit_allow_set.add(normalized)

        return col_roles, unit_allow_set, require_qty

    def save_schema_config(
        self,
        markup,
        sheet_index: int,
        col_roles: List[str],
        unit_allow_raw: str,
        require_qty: bool,
    ) -> None:
        """Сохраняет конфигурацию схемы"""
        annotation = markup.annotation or {}
        schema = annotation.get("schema", {})
        sheets_schema = schema.get("sheets", {})

        sheet_config = sheets_schema.get(str(sheet_index), {})
        sheet_config.update(
            {
                "col_roles": col_roles,
                "unit_allow_raw": unit_allow_raw,
                "require_qty": require_qty,
            }
        )

        sheets_schema[str(sheet_index)] = sheet_config
        schema["sheets"] = sheets_schema
        annotation["schema"] = schema

        markup.annotation = annotation
        markup.save(update_fields=["annotation"])
