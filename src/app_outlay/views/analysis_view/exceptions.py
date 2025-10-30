"""
Доменные исключения для анализа сметы.
"""


class AnalysisError(Exception):
    """Базовое исключение для ошибок анализа."""

    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class EstimateNotFoundError(AnalysisError):
    """Смета не найдена."""

    def __init__(self, estimate_id: int):
        super().__init__(
            message=f"Смета с ID {estimate_id} не найдена",
            details={"estimate_id": estimate_id},
        )


class NoTechnicalCardsError(AnalysisError):
    """В смете нет привязанных техкарт."""

    def __init__(self, estimate_id: int):
        super().__init__(
            message="В смете нет привязанных техкарт для анализа",
            details={"estimate_id": estimate_id},
        )
