"""
Кастомные исключения для модуля расчёта сметы.

Принципы:
- Явная обработка ошибок
- Разделение типов ошибок по назначению
- Удобная отладка через сообщения исключений
"""


class EstimateCalcException(Exception):
    """Базовое исключение для модуля расчёта сметы."""

    pass


class EstimateNotFoundError(EstimateCalcException):
    """Смета не найдена."""

    def __init__(self, estimate_id: int):
        self.estimate_id = estimate_id
        super().__init__(f"Смета с ID {estimate_id} не найдена")


class InvalidCalculationParamsError(EstimateCalcException):
    """Некорректные параметры расчёта."""

    def __init__(self, message: str):
        super().__init__(f"Некорректные параметры расчёта: {message}")


class TechnicalCardNotFoundError(EstimateCalcException):
    """Техническая карта не найдена."""

    def __init__(self, tc_id: int):
        self.tc_id = tc_id
        super().__init__(f"Техническая карта с ID {tc_id} не найдена")


class OverheadContextCalculationError(EstimateCalcException):
    """Ошибка расчёта контекста накладных расходов."""

    def __init__(self, message: str):
        super().__init__(f"Ошибка расчёта контекста НР: {message}")
