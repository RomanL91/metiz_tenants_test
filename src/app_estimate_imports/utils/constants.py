"""Константы для системы импорта смет"""

# Роли колонок (код, заголовок, цвет, обязательность)
ROLE_DEFS_RAW = [
    ("NONE", "—", None, False),
    # обязательные для «захвата» ТК/работ
    ("NAME_OF_WORK", "НАИМЕНОВАНИЕ РАБОТ/ТК", "#E3F2FD", True),
    ("UNIT", "ЕД. ИЗМ.", "#FFF8E1", True),
    ("QTY", "КОЛ-ВО", "#E8F5E9", True),
    # опциональные стоимости
    ("UNIT_PRICE_OF_MATERIAL", "ЦЕНА МАТ/ЕД", "#F3E5F5", False),
    ("UNIT_PRICE_OF_WORK", "ЦЕНА РАБОТЫ/ЕД", "#EDE7F6", False),
    ("UNIT_PRICE_OF_MATERIALS_AND_WORKS", "ЦЕНА МАТ+РАБ/ЕД", "#E1F5FE", False),
    ("PRICE_FOR_ALL_MATERIAL", "ИТОГО МАТЕРИАЛ", "#FBE9E7", False),
    ("PRICE_FOR_ALL_WORK", "ИТОГО РАБОТА", "#FFF3E0", False),
    ("TOTAL_PRICE", "ОБЩАЯ ЦЕНА", "#FFEBEE", False),
]

# Преобразуем в удобные представления
ROLE_DEFS = [
    {"id": rid, "title": title, "color": color or "#ffffff", "required": required}
    for (rid, title, color, required) in ROLE_DEFS_RAW
]

ROLE_IDS = [r["id"] for r in ROLE_DEFS]
REQUIRED_ROLE_IDS = [r["id"] for r in ROLE_DEFS if r["required"]]

# Типы узлов для разметки
NODE_TYPES = {
    "TECH_CARD": "Техкарта",
    "WORK": "Работа",
    "MATERIAL": "Материал",
    "GROUP": "Группа",
}

# Цвета для различных типов узлов
NODE_COLORS = {
    "TECH_CARD": "#a5d6a7",
    "WORK": "#81c784",
    "MATERIAL": "#ffb74d",
    "GROUP": "#90caf9",
    "root": "#bdbdbd",
}

# Роли узлов по источнику
NODE_ROLES = {
    "SHEET": "Лист",
    "UR1": "Уровень 1",
    "UR2": "Уровень 2",
    "UR3": "Уровень 3",
    "UR4": "Уровень 4",
    "SHIFR": "Шифр",
    "NAME": "Наименование",
}
