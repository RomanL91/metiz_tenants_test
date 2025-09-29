"""Сервис для построения графов из данных разметки"""

from typing import Dict, List, Tuple, Optional, Set
from .base_service import BaseService
from .markup_service import MarkupService
from .schema_service import SchemaService
from .group_service import GroupService
from ..utils.constants import NODE_COLORS, NODE_ROLES


class GraphService(BaseService):
    """Сервис для построения графических представлений данных"""

    def __init__(self):
        super().__init__()
        self.markup_service = MarkupService()
        self.schema_service = SchemaService()
        self.group_service = GroupService()

    def build_graph_from_markup(self, file_obj, sheet_index: int = 0) -> Dict:
        """Строит граф из разметки файла"""
        try:
            parse_result = getattr(file_obj, "parse_result", None)
            if not parse_result:
                self.add_error("Нет ParseResult для файла")
                return {"nodes": [], "edges": []}

            markup = self.markup_service.ensure_markup_exists(file_obj)
            labels = self.markup_service.get_labels(markup)
            tech_cards = self.markup_service.get_tech_cards(markup)
            groups = self.group_service.load_groups(markup, sheet_index)

            # Построение графа
            nodes, edges = self._build_graph_structure(
                parse_result.data, sheet_index, labels, tech_cards, groups
            )

            return {"nodes": nodes, "edges": edges}

        except Exception as e:
            self.add_error(f"Ошибка построения графа: {e}")
            return {"nodes": [], "edges": []}

    def build_graph_from_grid(self, file_obj, sheet_index: int = 0) -> Dict:
        """Строит граф на основе табличных данных"""
        try:
            parse_result = getattr(file_obj, "parse_result", None)
            # print(f"[DEBUG] [build_graph_from_grid] parse_result -- > {parse_result}")

            if not parse_result:
                self.add_error("Нет ParseResult для файла")
                return {"nodes": [], "edges": []}

            markup = self.markup_service.ensure_markup_exists(file_obj)
            # print(f"[DEBUG] [build_graph_from_grid] markup -- > {markup}")

            col_roles, unit_allow_set, require_qty = (
                self.schema_service.get_schema_config(markup, sheet_index)
            )
            # print(f"[DEBUG] [build_graph_from_grid] col_roles -- > {col_roles}")
            # print(
            #     f"[DEBUG] [build_graph_from_grid] unit_allow_set -- > {unit_allow_set}"
            # )
            # print(f"[DEBUG] [build_graph_from_grid] require_qty -- > {require_qty}")

            # Определение техкарт из табличных данных
            tech_cards = self._detect_techcards_from_grid(
                parse_result.data, sheet_index, col_roles, unit_allow_set, require_qty
            )

            # Получение групп
            groups = self.group_service.load_groups(markup, sheet_index)

            # print(f"[DEBUG] [build_graph_from_grid] groups -- > {groups}")

            # Построение графа для табличных данных
            nodes, edges = self._build_grid_graph(
                parse_result.data, sheet_index, col_roles, tech_cards, groups
            )

            # print(f"[DEBUG] [build_graph_from_grid] nodes -- > {nodes}")
            # print(f"[DEBUG] [build_graph_from_grid] = -- > {'='*33}")
            # print(f"[DEBUG] [build_graph_from_grid] edges -- > {edges}")

            return {"nodes": nodes, "edges": edges}

        except Exception as e:
            self.add_error(f"Ошибка построения графа из таблицы: {e}")
            return {"nodes": [], "edges": []}

    def _build_graph_structure(
        self,
        data: Dict,
        sheet_index: int,
        labels: Dict[str, str],
        tech_cards: List[Dict],
        groups: List[Dict],
    ) -> Tuple[List[Dict], List[Dict]]:
        """Строит структуру графа из размеченных данных"""
        nodes = []
        edges = []

        # Корневой узел листа
        sheets = data.get("sheets", [])
        if sheet_index < len(sheets):
            sheet = sheets[sheet_index]
            sheet_name = sheet.get("name", f"Лист {sheet_index + 1}")
        else:
            sheet_name = f"Лист {sheet_index + 1}"

        root_id = f"sheet:{sheet_index}"
        nodes.append(
            {
                "data": {
                    "id": root_id,
                    "label": f"Лист: {sheet_name}",
                    "type": "root",
                    "color": NODE_COLORS["root"],
                    "role": NODE_ROLES["SHEET"],
                }
            }
        )

        # Группы как узлы
        group_nodes = self._create_group_nodes(groups, sheet_index)
        nodes.extend(group_nodes)

        # Связи между группами и корнем
        group_edges = self._create_group_edges(groups, root_id)
        edges.extend(group_edges)

        # Узлы из разметки (техкарты, работы, материалы)
        markup_nodes, markup_edges = self._create_markup_nodes_and_edges(
            labels, tech_cards, groups, root_id
        )
        nodes.extend(markup_nodes)
        edges.extend(markup_edges)

        return nodes, edges

    def _build_grid_graph(
        self,
        data: Dict,
        sheet_index: int,
        col_roles: List[str],
        tech_cards: List[Dict],
        groups: List[Dict],
    ) -> Tuple[List[Dict], List[Dict]]:
        """Строит граф для табличного представления"""
        nodes = []
        edges = []

        # Корневой узел
        sheets = data.get("sheets", [])
        sheet_name = (
            sheets[sheet_index].get("name", f"Лист {sheet_index + 1}")
            if sheet_index < len(sheets)
            else f"Лист {sheet_index + 1}"
        )

        root_id = f"sheet:{sheet_index}"
        nodes.append(
            {
                "data": {
                    "id": root_id,
                    "label": f"Лист: {sheet_name}",
                    "type": "root",
                    "color": NODE_COLORS["root"],
                }
            }
        )

        # Группы
        group_nodes = self._create_group_nodes(groups, sheet_index)
        nodes.extend(group_nodes)
        group_edges = self._create_group_edges(groups, root_id)
        edges.extend(group_edges)

        # Техкарты из табличных данных
        tc_nodes, tc_edges = self._create_techcard_nodes_from_grid(
            tech_cards, groups, root_id
        )
        nodes.extend(tc_nodes)
        edges.extend(tc_edges)

        return nodes, edges

    def _create_group_nodes(self, groups: List[Dict], sheet_index: int) -> List[Dict]:
        """Создает узлы групп"""
        nodes = []

        for group in groups:
            group_id = f"g:{group['uid']}"
            nodes.append(
                {
                    "data": {
                        "id": group_id,
                        "label": group.get("name", "Группа"),
                        "type": "group",
                        "color": group.get("color", NODE_COLORS["GROUP"]),
                        "rows": group.get("rows", []),
                    }
                }
            )

        return nodes

    def _create_group_edges(self, groups: List[Dict], root_id: str) -> List[Dict]:
        """Создает связи между группами"""
        edges = []
        group_by_uid = {g["uid"]: g for g in groups}

        for group in groups:
            group_id = f"g:{group['uid']}"
            parent_uid = group.get("parent_uid")

            if parent_uid and parent_uid in group_by_uid:
                parent_id = f"g:{parent_uid}"
            else:
                parent_id = root_id

            edges.append(
                {
                    "data": {
                        "id": f"e:{parent_id}->{group_id}",
                        "source": parent_id,
                        "target": group_id,
                        "type": "hierarchy",
                    }
                }
            )

        return edges

    def _create_markup_nodes_and_edges(
        self,
        labels: Dict[str, str],
        tech_cards: List[Dict],
        groups: List[Dict],
        root_id: str,
    ) -> Tuple[List[Dict], List[Dict]]:
        """Создает узлы и связи из разметки"""
        nodes = []
        edges = []

        # Узлы по меткам
        for uid, label in labels.items():
            if label in NODE_COLORS:
                nodes.append(
                    {
                        "data": {
                            "id": uid,
                            "label": self._get_node_title(uid, label),
                            "type": label.lower(),
                            "color": NODE_COLORS[label],
                            "original_uid": uid,
                        }
                    }
                )

        # Связи техкарт с работами и материалами
        for tc in tech_cards:
            tc_uid = tc.get("uid")
            if not tc_uid:
                continue

            # Связи с работами
            for work_uid in tc.get("works", []):
                if work_uid in labels:
                    edges.append(
                        {
                            "data": {
                                "id": f"e:{tc_uid}->w:{work_uid}",
                                "source": tc_uid,
                                "target": work_uid,
                                "type": "contains_work",
                            }
                        }
                    )

            # Связи с материалами
            for material_uid in tc.get("materials", []):
                if material_uid in labels:
                    edges.append(
                        {
                            "data": {
                                "id": f"e:{tc_uid}->m:{material_uid}",
                                "source": tc_uid,
                                "target": material_uid,
                                "type": "contains_material",
                            }
                        }
                    )

        # Привязка узлов к группам или корню
        self._attach_nodes_to_groups(nodes, edges, groups, root_id)

        return nodes, edges

    def _attach_nodes_to_groups(
        self, nodes: List[Dict], edges: List[Dict], groups: List[Dict], root_id: str
    ) -> None:
        """Привязывает узлы к соответствующим группам"""
        # Простая логика: узлы без явной привязки идут к корню
        for node in nodes:
            node_id = node["data"]["id"]
            if node["data"].get("type") not in ["root", "group"]:
                # Можно добавить логику определения родительской группы
                # Пока все узлы привязываем к корню
                edges.append(
                    {
                        "data": {
                            "id": f"e:{root_id}->{node_id}",
                            "source": root_id,
                            "target": node_id,
                            "type": "contains",
                        }
                    }
                )

    def _detect_techcards_from_grid(
        self,
        data: Dict,
        sheet_index: int,
        col_roles: List[str],
        unit_allow_set: Set[str],
        require_qty: bool,
    ) -> List[Dict]:
        """Определяет техкарты из табличных данных"""
        sheets = data.get("sheets", [])
        if sheet_index >= len(sheets):
            return []

        sheet = sheets[sheet_index]
        rows = sheet.get("rows", [])

        # Индексы колонок по ролям
        name_cols = [i for i, r in enumerate(col_roles) if r == "NAME_OF_WORK"]
        unit_cols = [i for i, r in enumerate(col_roles) if r == "UNIT"]
        qty_cols = [i for i, r in enumerate(col_roles) if r == "QTY"]

        tech_cards = []

        for row_idx, row in enumerate(rows):
            cells = row.get("cells", [])

            # Проверка наличия имени
            has_name = any(
                (cells[i] if i < len(cells) else "").strip() for i in name_cols
            )
            if not has_name:
                continue

            # Проверка единицы измерения
            unit_raw = ""
            for i in unit_cols:
                if i < len(cells) and cells[i]:
                    unit_raw = cells[i].strip()
                    break

            unit_norm = self.schema_service.normalize_unit(unit_raw)
            has_valid_unit = bool(unit_norm) and (
                not unit_allow_set or unit_norm in unit_allow_set
            )

            # Проверка количества
            has_qty = True
            if require_qty:
                has_qty = any(
                    self._is_valid_quantity(cells[i] if i < len(cells) else "")
                    for i in qty_cols
                )

            if has_name and has_valid_unit and has_qty:
                name = next(
                    (
                        cells[i].strip()
                        for i in name_cols
                        if i < len(cells) and cells[i]
                    ),
                    f"ТК {row_idx}",
                )

                tech_cards.append(
                    {"id": f"tc:{row_idx}", "name": name, "row_index": row_idx}
                )

        return tech_cards

    def _create_techcard_nodes_from_grid(
        self, tech_cards: List[Dict], groups: List[Dict], root_id: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """Создает узлы техкарт из табличных данных"""
        nodes = []
        edges = []

        for tc in tech_cards:
            tc_id = tc["id"]
            nodes.append(
                {
                    "data": {
                        "id": tc_id,
                        "label": tc["name"],
                        "type": "tc",
                        "color": NODE_COLORS["TECH_CARD"],
                        "row_index": tc.get("row_index"),
                    }
                }
            )

            # Определение родительской группы
            parent_id = self._find_covering_group(tc.get("row_index"), groups)
            if not parent_id:
                parent_id = root_id

            edges.append(
                {
                    "data": {
                        "id": f"e:{parent_id}->{tc_id}",
                        "source": parent_id,
                        "target": tc_id,
                        "type": "contains",
                    }
                }
            )

        return nodes, edges

    def _find_covering_group(
        self, row_index: Optional[int], groups: List[Dict]
    ) -> Optional[str]:
        """Находит группу, покрывающую указанную строку"""
        if row_index is None:
            return None

        # Ищем самую глубокую группу, покрывающую строку
        covering_groups = []

        for group in groups:
            for start, end in group.get("rows", []):
                if start <= row_index <= end:
                    covering_groups.append(group)
                    break

        if not covering_groups:
            return None

        # Находим группу с максимальной глубиной
        def get_depth(group):
            depth = 0
            parent_uid = group.get("parent_uid")
            while parent_uid:
                parent = next((g for g in groups if g["uid"] == parent_uid), None)
                if not parent:
                    break
                depth += 1
                parent_uid = parent.get("parent_uid")
            return depth

        deepest_group = max(covering_groups, key=get_depth)
        return f"g:{deepest_group['uid']}"

    def _is_valid_quantity(self, value: str) -> bool:
        """Проверяет, является ли значение валидным количеством"""
        if not value:
            return False

        clean_value = value.replace(" ", "").replace(",", ".")
        try:
            num = float(clean_value)
            return num > 0
        except (ValueError, TypeError):
            return False

    def _get_node_title(self, uid: str, label: str) -> str:
        """Получает заголовок узла по UID и метке"""
        # Можно расширить логику получения названий из разметки
        if label == "TECH_CARD":
            return f"ТК: {uid[-8:]}"
        elif label == "WORK":
            return f"Работа: {uid[-8:]}"
        elif label == "MATERIAL":
            return f"Материал: {uid[-8:]}"
        else:
            return f"Группа: {uid[-8:]}"
