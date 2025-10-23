from rest_framework import serializers

from app_outlay.models import Estimate


class EstimateSettingsSerializer(serializers.ModelSerializer):
    """Сериализатор для работы с настройками сметы."""

    class Meta:
        model = Estimate
        fields = ["id", "name", "settings_data"]
        read_only_fields = ["id", "name"]

    def validate_settings_data(self, value):
        """Проверка, что settings_data - это словарь."""
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "settings_data должен быть словарём (объектом JSON)."
            )
        return value
