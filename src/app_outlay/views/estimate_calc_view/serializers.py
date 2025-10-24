"""
Сериализаторы для валидации входных данных API расчёта сметы.

Ответственность:
- Валидация query параметров
- Нормализация данных (например, замена запятой на точку)
- Документирование API схемы

Принципы:
- Single Responsibility: только валидация
- Fail Fast: ошибки валидации выбрасываются сразу
- Clear Messages: понятные сообщения об ошибках
"""

from rest_framework import serializers


class EstimateCalcQuerySerializer(serializers.Serializer):
    """
    Сериализатор для query параметров расчёта ТК.

    GET /api/estimate/{id}/calc/?tc=123&qty=10.5
    """

    tc = serializers.IntegerField(
        required=True,
        min_value=1,
        help_text="ID технической карты или версии ТК",
        error_messages={
            "required": "Параметр 'tc' обязателен",
            "invalid": "Параметр 'tc' должен быть целым числом",
            "min_value": "Параметр 'tc' должен быть больше 0",
        },
    )

    qty = serializers.CharField(
        required=True,
        help_text="Количество (может содержать запятую вместо точки)",
        error_messages={
            "required": "Параметр 'qty' обязателен",
            "invalid": "Параметр 'qty' должен быть числом",
        },
    )

    def validate_qty(self, value: str) -> float:
        """
        Валидация и нормализация количества.

        Принимает:
        - "10.5" (точка)
        - "10,5" (запятая)
        - "10" (целое)

        Args:
            value: Строковое значение количества

        Returns:
            float значение количества

        Raises:
            ValidationError: Если значение не является числом или < 0
        """
        # Нормализация: замена запятой на точку
        normalized = value.replace(",", ".")

        try:
            qty = float(normalized)
        except (ValueError, TypeError):
            raise serializers.ValidationError(f"Значение '{value}' не является числом")

        # Проверка диапазона
        if qty < 0:
            raise serializers.ValidationError("Количество не может быть отрицательным")

        return qty


class EstimateCalcResponseSerializer(serializers.Serializer):
    """
    Сериализатор для ответа API расчёта ТК.

    Используется для документирования API схемы (drf-spectacular).
    """

    ok = serializers.BooleanField(
        default=True,
        help_text="Успешность операции",
    )

    calc = serializers.DictField(
        child=serializers.FloatField(),
        help_text="Словарь расчётов по ключам (UNIT_PRICE_OF_MATERIAL, etc)",
    )

    order = serializers.ListField(
        child=serializers.CharField(),
        help_text="Порядок ключей для отображения",
    )

    class Meta:
        ref_name = "EstimateCalcResponse"


class ErrorResponseSerializer(serializers.Serializer):
    """
    Сериализатор для ответа с ошибкой.

    Единый формат для всех ошибок API.
    """

    ok = serializers.BooleanField(
        default=False,
        help_text="Успешность операции (всегда False при ошибке)",
    )

    error = serializers.CharField(
        help_text="Описание ошибки",
    )

    class Meta:
        ref_name = "ErrorResponse"
