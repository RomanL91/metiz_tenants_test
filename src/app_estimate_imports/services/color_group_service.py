"""
Сервис для автоматического создания групп на основе цветовой разметки.

Назначение:
-----------
Анализирует цвета ячеек в колонке NAME_OF_WORK и автоматически создаёт
иерархическую структуру групп/подгрупп для удобной навигации и организации данных.

Алгоритм:
---------
1. Строка с цветом + пустые UNIT/QTY = начало группы/подгруппы
2. Имя группы = текст из ячейки NAME_OF_WORK
3. Конец группы = следующая строка с таким же цветом (или конец файла)
4. Новый цвет внутри группы = вложенная подгруппа (level+1, parent=текущая)
5. Стек активных групп отслеживает иерархию

Пример:
-------
Строка 0: 🔵 "Раздел 1"       → Группа1, level=0, rows=[0-4]
Строка 1:    "Работа 1"       → внутри Группа1
Строка 2:    "Работа 2"       → внутри Группа1
Строка 3: 🟢 "Подраздел 1.1"  → Группа2, level=1, parent=Группа1, rows=[3-4]
Строка 4:    "Работа 3"       → внутри Группа1 И Группа2
Строка 5: 🔵 "Раздел 2"       → закрывает Группа1(0-4) и Группа2(3-4), новая Группа3
"""

import logging
import secrets
from typing import Dict, List, Optional, Tuple

from app_estimate_imports.services.base_service import BaseService
from app_estimate_imports.services.group_service import GroupService

logger = logging.getLogger(__name__)


class ColorGroupService(BaseService):
    """Сервис автоматического создания групп по цветам"""

    def __init__(self):
        super().__init__()
        self.group_service = GroupService()

    def analyze_colors_and_create_groups(
        self,
        markup,
        sheet_index: int,
        name_of_work_col_index: int,
        warn_if_groups_exist: bool = True,
        hidden_rows: Optional[List[int]] | None = None,
        hidden_cols: Optional[List[int]] | None = None,
    ) -> Dict:
        """
        Анализирует цвета и создаёт иерархическую структуру групп.

        Args:
            markup: Объект ParseMarkup с annotation
            sheet_index: Индекс листа Excel (0-based)
            name_of_work_col_index: Индекс колонки NAME_OF_WORK
            warn_if_groups_exist: Если True, требует подтверждения при наличии групп

        Returns:
            {
                "ok": bool,
                "groups_created": int,
                "had_existing_groups": bool,
                "requires_confirmation": bool (опционально),
                "error": str (опционально)
            }
        """
        try:
            logger.info("=" * 80)
            logger.info(
                f"🔍 НАЧАЛО АНАЛИЗА | Лист: {sheet_index}, Колонка NAME_OF_WORK: {name_of_work_col_index}"
            )
            logger.info("=" * 80)

            # 1. Проверка существующих групп
            existing_groups = self.group_service.load_groups(markup, sheet_index)
            if existing_groups and warn_if_groups_exist:
                logger.warning(
                    f"⚠️ Найдено {len(existing_groups)} существующих групп, требуется подтверждение"
                )
                return {
                    "ok": False,
                    "requires_confirmation": True,
                    "had_existing_groups": True,
                    "error": f"Найдено существующих групп: {len(existing_groups)}",
                }

            # Удаляем старые группы если force=True (warn_if_groups_exist=False)
            had_existing = len(existing_groups) > 0
            if existing_groups and not warn_if_groups_exist:
                logger.info(f"🗑️ Удаляем {len(existing_groups)} существующих групп")
                self._clear_all_groups(markup, sheet_index)

            # 2. Получение данных листа
            parse_result = markup.parse_result
            if not parse_result or not parse_result.data:
                return {"ok": False, "error": "ParseResult не содержит данных"}

            sheets = parse_result.data.get("sheets", [])
            if sheet_index >= len(sheets):
                return {"ok": False, "error": f"Лист {sheet_index} не найден"}

            sheet = sheets[sheet_index]
            rows = sheet.get("rows", [])

            hidden_rows_set = {int(r) for r in (hidden_rows or [])}
            if hidden_rows_set:
                rows = [
                    row
                    for idx, row in enumerate(rows, start=1)
                    if row.get("row_index", idx) not in hidden_rows_set
                ]


            if not rows:
                return {
                    "ok": True,
                    "groups_created": 0,
                    "had_existing_groups": had_existing,
                }

            logger.info(f"📊 Всего строк в листе: {len(rows)}")

            # 3. Определение колонок UNIT и QTY из схемы
            hidden_cols_set = {int(c) for c in (hidden_cols or [])}

            if name_of_work_col_index in hidden_cols_set:
                return {
                    "ok": False,
                    "error": "Колонка NAME_OF_WORK скрыта, создание групп невозможно",
                }

            unit_cols, qty_cols = self._get_validation_columns(markup, sheet_index)
            unit_cols = self._filter_hidden_columns(unit_cols, hidden_cols_set)
            qty_cols = self._filter_hidden_columns(qty_cols, hidden_cols_set)
            logger.info(f"📋 Колонки UNIT: {unit_cols}, колонки QTY: {qty_cols}")

            # 4. Анализ строк и построение групп
            groups_to_create = self._analyze_rows_and_build_groups(
                rows=rows,
                name_col=name_of_work_col_index,
                unit_cols=unit_cols,
                qty_cols=qty_cols,
                hidden_cols=hidden_cols_set,
            )

            if not groups_to_create:
                logger.warning("❌ Не найдено ни одной группы с цветовой разметкой")
                self.add_warning("Не найдено ни одной группы с цветовой разметкой")
                return {
                    "ok": True,
                    "groups_created": 0,
                    "had_existing_groups": had_existing,
                }

            logger.info(f"\n✅ ГОТОВО К СОЗДАНИЮ: {len(groups_to_create)} групп")
            self._log_groups_structure(groups_to_create)

            # 5. Создание групп через GroupService
            created_count = self._create_groups_in_markup(
                markup=markup,
                sheet_index=sheet_index,
                groups_to_create=groups_to_create,
            )

            logger.info(f"\n🎉 УСПЕШНО СОЗДАНО: {created_count} групп")
            logger.info("=" * 80)

            return {
                "ok": True,
                "groups_created": created_count,
                "had_existing_groups": had_existing,
            }

        except Exception as e:
            logger.exception(f"💥 ОШИБКА: {str(e)}")
            self.add_error(f"Ошибка анализа цветов: {str(e)}")
            return {"ok": False, "error": str(e)}

    def _get_validation_columns(
        self, markup, sheet_index: int
    ) -> Tuple[List[int], List[int]]:
        """
        Получает индексы колонок UNIT и QTY из схемы.

        Эти колонки используются для валидации: если у строки есть цвет,
        но заполнены UNIT/QTY — это не группа, а работа/ТК.
        """
        annotation = markup.annotation or {}
        schema = annotation.get("schema", {})
        sheets = schema.get("sheets", {})
        sheet_config = sheets.get(str(sheet_index), {})
        col_roles = sheet_config.get("col_roles", [])

        unit_cols = [i for i, role in enumerate(col_roles) if role == "UNIT"]
        qty_cols = [i for i, role in enumerate(col_roles) if role == "QTY"]

        return unit_cols, qty_cols

    def _normalize_color(self, color: Optional[str]) -> Optional[str]:
        """
        Нормализует цвет к единому формату #RRGGBB.

        Обрабатывает:
        - None/пустая строка → None
        - #RRGGBB → #RRGGBB (uppercase)
        - RRGGBB → #RRGGBB
        - #RGB → #RRGGBB (удвоение символов)
        """
        if not color:
            return None

        color = color.strip().upper()

        # Убираем # если есть
        if color.startswith("#"):
            color = color[1:]

        # Проверяем формат
        if len(color) == 6 and all(c in "0123456789ABCDEF" for c in color):
            return f"#{color}"
        elif len(color) == 3 and all(c in "0123456789ABCDEF" for c in color):
            # #RGB → #RRGGBB
            return f"#{color[0]}{color[0]}{color[1]}{color[1]}{color[2]}{color[2]}"

        return None

    def _analyze_rows_and_build_groups(
        self,
        rows: List[Dict],
        name_col: int,
        unit_cols: List[int],
        qty_cols: List[int],
        hidden_cols: set[int],
    ) -> List[Dict]:
        """
        Главный алгоритм: проход по строкам и построение структуры групп.

        Использует стек активных групп для отслеживания иерархии:
        - Новый цвет = новый уровень вложенности
        - Повторный цвет = закрытие групп и начало на том же уровне
        - Строка без цвета = работа, входит во все активные группы

        Returns:
            Список словарей с информацией о группах (готовых к созданию)
        """
        completed_groups = []  # Завершённые группы с финальными диапазонами
        active_stack = []  # Стек: [{group_data, color, start_row, row_index}]

        # Статистика для отладки
        total_colored_rows = 0
        filtered_by_unit_qty = 0
        filtered_by_empty_name = 0
        skipped_headers = 0

        # Определяем начало данных (пропускаем заголовки)
        data_start_idx = self._find_data_start(
            rows, name_col, unit_cols, qty_cols, hidden_cols
        )
        logger.info(
            f"🔍 Начало данных определено на строке с индексом: {data_start_idx}"
        )

        logger.info("\n" + "=" * 80)
        logger.info("📝 АНАЛИЗ СТРОК (детали первых 20 строк после заголовков)")
        logger.info("=" * 80)

        for row_idx, row_data in enumerate(rows):
            # Пропускаем строки-заголовки
            if row_idx < data_start_idx:
                skipped_headers += 1
                if row_idx < 10:
                    logger.info(
                        f"\nСтрока {row_data.get('row_index', row_idx + 1):3d} (idx={row_idx}): "
                        f"ПРОПУЩЕНА (заголовок)"
                    )
                continue

            cells = row_data.get("cells", [])
            colors = row_data.get("colors", [])

            # ВАЖНО: row_index из данных (может отличаться от row_idx)
            # В grid.html используется r.row_index, а не индекс в массиве
            actual_row_index = row_data.get("row_index", row_idx + 1)

            # Получаем данные текущей строки
            name = self._get_cell_value(cells, name_col, hidden_cols)
            raw_color = self._get_cell_value(colors, name_col, hidden_cols)
            color = self._normalize_color(raw_color)

            # Получаем значения UNIT и QTY для отладки
            unit_values = [self._get_cell_value(cells, c, hidden_cols) for c in unit_cols]
            qty_values = [self._get_cell_value(cells, c, hidden_cols) for c in qty_cols]

            # Строгая проверка UNIT/QTY: пустая строка, None, или только пробелы = пусто
            has_unit = self._has_meaningful_value_in_columns(cells, unit_cols, hidden_cols)
            has_qty = self._has_meaningful_value_in_columns(cells, qty_cols, hidden_cols)

            # Проверяем, есть ли осмысленный текст в NAME_OF_WORK
            has_meaningful_name = name and len(name.strip()) > 0

            # Детальный лог первых 20 строк данных
            if row_idx < data_start_idx + 20:
                name_short = (
                    (name[:40] + "...") if name and len(name) > 40 else (name or "")
                )
                stack_repr = self._format_stack(active_stack)

                logger.info(f"\nСтрока {actual_row_index:3d} (idx={row_idx}):")
                logger.info(f"  📝 Название: '{name_short}'")
                logger.info(f"  🎨 Цвет: {raw_color} → {color or 'нет'}")
                logger.info(f"  ✍️  Текст: {'ЕСТЬ' if has_meaningful_name else 'ПУСТОЙ'}")
                logger.info(
                    f"  📏 UNIT: {unit_values} → {'ЕСТЬ' if has_unit else 'нет'}"
                )
                logger.info(f"  🔢 QTY:  {qty_values} → {'ЕСТЬ' if has_qty else 'нет'}")
                logger.info(f"  📚 Стек: {len(active_stack)} уровней {stack_repr}")

            # Проверка: это начало группы?
            if color:
                total_colored_rows += 1

                if has_unit or has_qty:
                    filtered_by_unit_qty += 1
                    if row_idx < data_start_idx + 20:
                        logger.info(f"  ⚠️ ПРОПУЩЕНО: имеет UNIT/QTY → не группа")
                    continue

                # НОВАЯ ПРОВЕРКА: пустая ячейка NAME_OF_WORK?
                if not has_meaningful_name:
                    filtered_by_empty_name += 1
                    if row_idx < data_start_idx + 20:
                        logger.info(
                            f"  ⚠️ ПРОПУЩЕНО: пустая ячейка NAME_OF_WORK → не группа"
                        )
                    continue

                # Это группа!
                if row_idx < data_start_idx + 20:
                    logger.info(f"  ✅ ЭТО ГРУППА!")

                level_to_close = self._find_group_level_by_color(active_stack, color)

                if level_to_close is not None:
                    # Закрываем группы с этого уровня и глубже
                    if row_idx < data_start_idx + 20:
                        logger.info(f"  🔄 Закрываю группы с уровня {level_to_close}")

                    closed = self._close_groups_from_level(
                        active_stack, level_to_close, actual_row_index - 1
                    )

                    for closed_group in closed:
                        if row_idx < data_start_idx + 20:
                            logger.info(
                                f"     📦 Закрыта: '{closed_group['name'][:30]}' "
                                f"[{closed_group['rows'][0][0]}-{closed_group['rows'][0][1]}] "
                                f"level={closed_group['level']}"
                            )

                    completed_groups.extend(closed)

                # Создаём новую группу
                level = len(active_stack)
                parent_uid = (
                    active_stack[-1]["group_data"]["uid"] if active_stack else None
                )
                parent_name = (
                    active_stack[-1]["group_data"]["name"] if active_stack else None
                )

                group_data = {
                    "uid": "grp_" + secrets.token_hex(8),
                    "name": (name or f"Группа {actual_row_index}").strip(),
                    "color": color,
                    "rows": [],  # Заполним при закрытии группы
                    "parent_uid": parent_uid,
                    "level": level,
                }

                if row_idx < data_start_idx + 20:
                    logger.info(f"  ➕ ОТКРЫТА ГРУППА:")
                    logger.info(f"     Название: '{group_data['name'][:40]}'")
                    logger.info(f"     Цвет: {color}")
                    logger.info(f"     Level: {level}")
                    logger.info(
                        f"     Родитель: {parent_name[:30] if parent_name else 'НЕТ'}"
                    )

                # Добавляем в стек
                active_stack.append(
                    {
                        "group_data": group_data,
                        "color": color,
                        "start_row": actual_row_index,
                        "row_index": actual_row_index,
                    }
                )

        # Закрываем все оставшиеся открытые группы
        if active_stack:
            last_row = rows[-1].get("row_index", len(rows))
            logger.info(
                f"\n🔚 Закрываю оставшиеся {len(active_stack)} групп в конце файла (строка {last_row})"
            )

            closed = self._close_groups_from_level(active_stack, 0, last_row)

            for closed_group in closed:
                logger.info(
                    f"  📦 Закрыта: '{closed_group['name'][:40]}' "
                    f"[{closed_group['rows'][0][0]}-{closed_group['rows'][0][1]}] "
                    f"level={closed_group['level']}"
                )

            completed_groups.extend(closed)

        # Итоговая статистика
        logger.info("\n" + "=" * 80)
        logger.info("📊 СТАТИСТИКА АНАЛИЗА")
        logger.info("=" * 80)
        logger.info(f"Пропущено заголовков: {skipped_headers}")
        logger.info(f"Обработано строк: {len(rows) - skipped_headers}")
        logger.info(f"Строк с цветом: {total_colored_rows}")
        logger.info(f"Отфильтровано (имеют UNIT/QTY): {filtered_by_unit_qty}")
        logger.info(f"Отфильтровано (пустое NAME_OF_WORK): {filtered_by_empty_name}")
        logger.info(f"Создано групп: {len(completed_groups)}")

        if completed_groups:
            unique_colors = set(g["color"] for g in completed_groups)
            logger.info(f"Уникальные цвета: {', '.join(sorted(unique_colors))}")

        return completed_groups

    def _find_data_start(
        self,
        rows: List[Dict],
        name_col: int,
        unit_cols: List[int],
        qty_cols: List[int],
        hidden_cols: set[int],
    ) -> int:
        """
        Определяет индекс строки, с которой начинаются данные (после заголовков).

        Логика:
        1. Ищем строку с заголовками колонок (содержит "НАИМЕНОВАНИЕ", "ЕД.ИЗМ", "КОЛ-ВО")
        2. Пропускаем все строки до этой включительно
        3. Пропускаем ещё одну строку после заголовков (если есть доп. заголовок)
        4. Возвращаем индекс первой строки с данными
        """
        header_keywords = ["НАИМЕНОВАНИЕ", "ЕД.ИЗМ", "КОЛ-ВО", "ШИФР", "П.П"]

        for row_idx, row_data in enumerate(rows):
            cells = row_data.get("cells", [])

            # Проверяем, есть ли ключевые слова заголовков
            name_value = self._get_cell_value(cells, name_col, hidden_cols)
            unit_value = (
                self._get_cell_value(cells, unit_cols[0], hidden_cols)
                if unit_cols
                else ""
            )
            qty_value = (
                self._get_cell_value(cells, qty_cols[0], hidden_cols)
                if qty_cols
                else ""
            )

            # Объединяем все значения для проверки
            all_text = " ".join(
                filter(None, [name_value or "", unit_value or "", qty_value or ""])
            ).upper()

            # Если нашли строку с заголовками
            if any(keyword in all_text for keyword in header_keywords):
                # Возвращаем следующую строку после заголовков
                # Обычно: строка с заголовками + 1 строка с номерами/доп.инфо + начало данных
                return min(row_idx + 2, len(rows))

        # Если заголовки не найдены, начинаем с первой строки
        return 0

    def _find_group_level_by_color(
        self, active_stack: List[Dict], color: str
    ) -> Optional[int]:
        """
        Ищет уровень группы с указанным цветом в стеке.

        Возвращает индекс уровня или None, если цвет не найден.
        """
        for idx, stack_item in enumerate(active_stack):
            if stack_item["color"] == color:
                return idx
        return None

    def _close_groups_from_level(
        self, active_stack: List[Dict], level: int, end_row: int
    ) -> List[Dict]:
        """
        Закрывает все группы начиная с указанного уровня.

        Для каждой группы устанавливает финальный диапазон rows.

        Returns:
            Список закрытых групп (готовых к созданию)
        """
        closed_groups = []

        while len(active_stack) > level:
            stack_item = active_stack.pop()
            group_data = stack_item["group_data"]
            start_row = stack_item["start_row"]

            # Устанавливаем диапазон [start, end]
            group_data["rows"] = [[start_row, end_row]]

            closed_groups.append(group_data)

        # Возвращаем в обратном порядке (чтобы родители были раньше потомков)
        return list(reversed(closed_groups))

    def _create_groups_in_markup(
        self, markup, sheet_index: int, groups_to_create: List[Dict]
    ) -> int:
        """
        Создаёт группы в разметке через GroupService.

        Важно: создаём в правильном порядке (сначала родители, потом потомки),
        чтобы parent_uid существовал к моменту создания дочерней группы.
        """
        # Сортируем по уровню (level), чтобы родители создавались раньше
        sorted_groups = sorted(groups_to_create, key=lambda g: g["level"])

        logger.info("\n" + "=" * 80)
        logger.info("💾 СОЗДАНИЕ ГРУПП В БД")
        logger.info("=" * 80)

        created_count = 0
        uid_mapping = {}  # Временный uid → реальный uid после создания

        for group_data in sorted_groups:
            try:
                # Заменяем parent_uid на реальный (если был временный)
                parent_uid = group_data["parent_uid"]
                if parent_uid and parent_uid in uid_mapping:
                    parent_uid = uid_mapping[parent_uid]

                logger.info(
                    f"\n➕ Создаю: '{group_data['name'][:40]}' "
                    f"| level={group_data['level']} | rows={group_data['rows']}"
                )

                # Создаём группу
                created_group = self.group_service.create_group(
                    markup=markup,
                    sheet_index=sheet_index,
                    name=group_data["name"],
                    rows=group_data["rows"],
                    parent_uid=parent_uid,
                    color=group_data["color"],
                )

                # Сохраняем маппинг временного uid → реального
                uid_mapping[group_data["uid"]] = created_group["uid"]

                created_count += 1
                logger.info(f"   ✅ Создана с uid: {created_group['uid']}")

            except Exception as e:
                logger.error(f"   ❌ ОШИБКА: {str(e)}")
                self.add_warning(
                    f"Не удалось создать группу '{group_data['name']}': {str(e)}"
                )
                continue

        return created_count

    def _clear_all_groups(self, markup, sheet_index: int):
        """Удаляет все существующие группы на листе"""
        groups = self.group_service.load_groups(markup, sheet_index)

        # Сначала собираем все uid групп верхнего уровня (без родителя)
        root_groups = [g for g in groups if not g.get("parent_uid")]

        # Удаляем только корневые группы (delete_group рекурсивно удалит потомков)
        for group in root_groups:
            try:
                self.group_service.delete_group(markup, sheet_index, group["uid"])
            except Exception as e:
                self.add_warning(f"Ошибка удаления группы {group['name']}: {str(e)}")

    # === Вспомогательные методы ===

    def _get_cell_value(
        self, array: List, index: int, hidden_cols: Optional[set[int]] = None
    ) -> Optional[str]:
        """Безопасно получает значение из массива по индексу, учитывая скрытые колонки."""
        if (hidden_cols and index in hidden_cols) or index < 0 or index >= len(array):
            return None
        value = array[index]
        return value.strip() if isinstance(value, str) and value else value

    def _has_meaningful_value_in_columns(
        self, cells: List, col_indices: List[int], hidden_cols: Optional[set[int]] = None
    ) -> bool:
        """
        Проверяет, есть ли ЗНАЧИМОЕ непустое значение в указанных колонках.

        Значимое = не None, не пустая строка, не только пробелы.
        """
        for col_idx in col_indices:
            value = self._get_cell_value(cells, col_idx, hidden_cols)
            # Проверяем: не None И не пустая строка после strip
            if value and len(value.strip()) > 0:
                return True
        return False
    
    def _filter_hidden_columns(
        self, col_indices: List[int], hidden_cols: set[int]
    ) -> List[int]:
        """Отбрасывает колонки, которые пользователь скрыл в гриде."""
        if not hidden_cols:
            return col_indices
        return [idx for idx in col_indices if idx not in hidden_cols]

    def _format_stack(self, stack: List[Dict]) -> str:
        """Форматирует стек для вывода в лог"""
        if not stack:
            return "[пусто]"
        return (
            "["
            + ", ".join(
                f"{item['color'][:7]}:{item['group_data']['name'][:15]}"
                for item in stack
            )
            + "]"
        )

    def _log_groups_structure(self, groups: List[Dict]):
        """Выводит древовидную структуру групп"""
        logger.info("\n📂 СТРУКТУРА ГРУПП:")

        # Группируем по parent_uid
        by_parent = {}
        for g in groups:
            parent = g.get("parent_uid") or "root"
            if parent not in by_parent:
                by_parent[parent] = []
            by_parent[parent].append(g)

        def print_tree(parent_uid, indent=0):
            children = by_parent.get(parent_uid, [])
            for child in children:
                logger.info(
                    f"{'  ' * indent}├─ {child['name'][:40]} "
                    f"[{child['rows'][0][0]}-{child['rows'][0][1]}] "
                    f"({child['color']})"
                )
                print_tree(child["uid"], indent + 1)

        print_tree("root")
