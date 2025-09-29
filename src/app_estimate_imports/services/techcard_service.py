"""Сервис для работы с техкартами"""

from typing import List, Dict, Set, Optional, Tuple
from .base_service import BaseService
from .markup_service import MarkupService
from .schema_service import SchemaService
from ..utils.hash_utils import HashUtils


class TechCardService(BaseService):
    """Сервис для управления техкартами и их составом"""

    def __init__(self):
        super().__init__()
        self.markup_service = MarkupService()
        self.schema_service = SchemaService()

    def detect_techcards_from_sheet(
        self,
        parse_result,
        sheet_index: int = 0,
        col_roles: Optional[List[str]] = None,
        unit_allow_set: Optional[Set[str]] = None,
        require_qty: bool = True,
    ) -> List[Dict]:
        """Определяет техкарты из данных листа"""
        sheets = parse_result.data.get("sheets", [])
        if sheet_index >= len(sheets):
            self.add_warning(f"Лист {sheet_index} не найден")
            return []

        sheet = sheets[sheet_index]
        rows = sheet.get("rows", [])

        if not col_roles:
            col_roles = self.schema_service.detect_column_roles(rows)

        if unit_allow_set is None:
            unit_allow_set = {"м2", "м3", "шт", "пм", "компл"}

        return self._scan_rows_for_techcards(
            rows, col_roles, unit_allow_set, require_qty
        )

    def get_techcard_composition(self, file_obj, tc_uid: str) -> Dict:
        """Получает состав техкарты"""
        try:
            markup = self.markup_service.ensure_markup_exists(file_obj)
            tech_cards = self.markup_service.get_tech_cards(markup)

            tc_entry = next((tc for tc in tech_cards if tc.get("uid") == tc_uid), None)

            if not tc_entry:
                self.add_warning(f"Техкарта {tc_uid} не найдена")
                return {"works": [], "materials": []}

            return {
                "uid": tc_entry.get("uid"),
                "works": tc_entry.get("works", []),
                "materials": tc_entry.get("materials", []),
                "name": tc_entry.get("name", ""),
            }

        except Exception as e:
            self.add_error(f"Ошибка получения состава ТК: {e}")
            return {"works": [], "materials": []}

    def update_techcard_composition(
        self,
        file_obj,
        tc_uid: str,
        works: List[str],
        materials: List[str],
        name: Optional[str] = None,
    ) -> bool:
        """Обновляет состав техкарты"""
        try:
            self.markup_service.set_tech_card_members(
                file_obj, tc_uid, works, materials
            )

            # Обновляем название если передано
            if name:
                self.markup_service.set_label(file_obj, tc_uid, "TECH_CARD", name)

            return True

        except Exception as e:
            self.add_error(f"Ошибка обновления состава ТК: {e}")
            return False

    def get_available_works_and_materials(
        self, file_obj
    ) -> Tuple[List[Dict], List[Dict]]:
        """Получает доступные работы и материалы для привязки к техкартам"""
        try:
            markup = self.markup_service.ensure_markup_exists(file_obj)
            labels = self.markup_service.get_labels(markup)

            # Получаем названия узлов
            annotation = markup.annotation or {}
            names = annotation.get("names", {})

            works = []
            materials = []

            for uid, label in labels.items():
                name = names.get(uid, uid)
                node_info = {"uid": uid, "name": name}

                if label == "WORK":
                    works.append(node_info)
                elif label == "MATERIAL":
                    materials.append(node_info)

            return works, materials

        except Exception as e:
            self.add_error(f"Ошибка получения работ и материалов: {e}")
            return [], []

    def validate_techcard_composition(
        self, works: List[str], materials: List[str]
    ) -> bool:
        """Валидирует состав техкарты"""
        if not works and not materials:
            self.add_error("Техкарта должна содержать хотя бы одну работу или материал")
            return False

        # Проверка на дубликаты
        if len(works) != len(set(works)):
            self.add_warning("Обнаружены дублирующиеся работы")

        if len(materials) != len(set(materials)):
            self.add_warning("Обнаружены дублирующиеся материалы")

        return True

    def _scan_rows_for_techcards(
        self,
        rows: List[Dict],
        col_roles: List[str],
        unit_allow_set: Set[str],
        require_qty: bool,
    ) -> List[Dict]:
        """Сканирует строки на предмет техкарт"""
        techcards = []

        # Индексы колонок по ролям
        name_cols = [i for i, r in enumerate(col_roles) if r == "NAME_OF_WORK"]
        unit_cols = [i for i, r in enumerate(col_roles) if r == "UNIT"]
        qty_cols = [i for i, r in enumerate(col_roles) if r == "QTY"]

        for row_idx, row in enumerate(rows):
            cells = row.get("cells", [])

            # Проверка наличия имени
            name = self._get_first_non_empty_value(cells, name_cols)
            if not name:
                continue

            # Проверка единицы измерения
            unit_raw = self._get_first_non_empty_value(cells, unit_cols)
            unit_norm = self.schema_service.normalize_unit(unit_raw)

            if not unit_norm or (unit_allow_set and unit_norm not in unit_allow_set):
                continue

            # Проверка количества
            if require_qty:
                has_valid_qty = any(
                    self._is_valid_quantity(cells[i] if i < len(cells) else "")
                    for i in qty_cols
                )
                if not has_valid_qty:
                    continue

            # Создаем запись о техкарте
            tc_uid = HashUtils.node_id(0, "TC", f"{row_idx}-{name}")
            techcards.append(
                {
                    "uid": tc_uid,
                    "name": name,
                    "row_index": row_idx,
                    "unit": unit_norm,
                    "row_data": cells,
                }
            )

        return techcards

    def _get_first_non_empty_value(self, cells: List, indices: List[int]) -> str:
        """Получает первое непустое значение из указанных индексов"""
        for idx in indices:
            if idx < len(cells) and cells[idx]:
                return str(cells[idx]).strip()
        return ""

    def _is_valid_quantity(self, value: str) -> bool:
        """Проверяет валидность количества"""
        if not value:
            return False

        clean_value = str(value).replace(" ", "").replace(",", ".")
        try:
            num = float(clean_value)
            return num > 0
        except (ValueError, TypeError):
            return False
