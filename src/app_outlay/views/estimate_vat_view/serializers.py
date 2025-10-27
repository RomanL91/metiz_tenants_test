"""
Сериализаторы для API НДС.
"""

from rest_framework import serializers


class VatStatusResponseSerializer(serializers.Serializer):
    """Ответ статуса НДС."""

    ok = serializers.BooleanField(default=True)
    vat_active = serializers.BooleanField(help_text="НДС активен")
    vat_rate = serializers.IntegerField(help_text="Ставка НДС в процентах (0-100)")


class VatToggleRequestSerializer(serializers.Serializer):
    """Запрос переключения НДС."""

    is_active = serializers.BooleanField(help_text="Активировать/деактивировать НДС")


class VatSetRateRequestSerializer(serializers.Serializer):
    """Запрос установки ставки НДС."""

    rate = serializers.IntegerField(
        min_value=0,
        max_value=100,
        help_text="Ставка НДС в процентах (0-100)",
    )


class ErrorResponseSerializer(serializers.Serializer):
    """Ответ с ошибкой."""

    ok = serializers.BooleanField(default=False)
    error = serializers.CharField()
