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
        help_text="ID технической карты (card_id)",
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


class BatchCalcItemSerializer(serializers.Serializer):
    """
    Сериализатор для одного элемента batch расчёта.
    """

    tc_id = serializers.IntegerField(
        required=True,
        min_value=1,
        help_text="ID технической карты (card_id)",
    )

    quantity = serializers.FloatField(
        required=True,
        min_value=0,
        help_text="Количество",
    )

    row_index = serializers.IntegerField(
        required=False,
        help_text="Индекс строки (опционально, для сопоставления в ответе)",
    )


class EstimateBatchCalcRequestSerializer(serializers.Serializer):
    """
    Сериализатор для batch запроса расчётов.

    POST /api/estimate/{id}/calc-batch/
    {
        "items": [
            {"tc_id": 123, "quantity": 10.5, "row_index": 0},
            {"tc_id": 456, "quantity": 20.0, "row_index": 1}
        ]
    }
    """

    items = serializers.ListField(
        child=BatchCalcItemSerializer(),
        min_length=1,
        max_length=1000,
        help_text="Список элементов для расчёта (макс. 1000)",
    )


class BatchCalcResultSerializer(serializers.Serializer):
    """
    Сериализатор для результата одного расчёта в batch.
    """

    tc_id = serializers.IntegerField()
    quantity = serializers.FloatField()
    row_index = serializers.IntegerField(required=False, allow_null=True)
    calc = serializers.DictField(child=serializers.FloatField())
    error = serializers.CharField(required=False, allow_null=True)


class EstimateBatchCalcResponseSerializer(serializers.Serializer):
    """
    Сериализатор для ответа batch расчётов.
    """

    ok = serializers.BooleanField(default=True)
    results = serializers.ListField(child=BatchCalcResultSerializer())
    order = serializers.ListField(child=serializers.CharField())


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
