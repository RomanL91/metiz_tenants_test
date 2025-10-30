from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

from app_outlay.models import EstimateOverheadCostLink, Estimate


@receiver([post_save, post_delete], sender=EstimateOverheadCostLink)
def invalidate_overhead_cache_on_link_change(sender, instance, **kwargs):
    """
    Инвалидация кеша при изменении EstimateOverheadCostLink.

    Срабатывает при:
    - Добавлении НР (через .create())
    - Изменении НР (через .save())
    - Удалении НР (через .delete())

    НЕ срабатывает при:
    - .update() (заменили на .save() в цикле)
    - .bulk_create() (вызываем вручную после операции)
    """
    estimate_id = instance.estimate_id

    pattern = f"oh_ctx:{estimate_id}:*"

    if hasattr(cache, "delete_pattern"):
        cache.delete_pattern(pattern)
    else:
        # Для не-Redis: инкремент версии
        _increment_cache_version(estimate_id)


@receiver(post_save, sender=Estimate)
def invalidate_overhead_cache_on_estimate_change(sender, instance, **kwargs):
    """
    Инвалидация кеша при изменении settings_data сметы.

    Срабатывает при:
    - Включении/выключении НДС
    - Изменении ставки НДС
    """
    # Пропускаем если это инкремент версии кеша (избегаем рекурсии)
    if kwargs.get("update_fields") == frozenset(["settings_data"]):
        # Проверяем что изменилась только версия кеша
        if instance.settings_data:
            changed_keys = set(instance.settings_data.keys())
            if changed_keys == {"overhead_cache_version"}:
                return  # Это наш инкремент, пропускаем

    # Обычная логика инвалидации
    if kwargs.get("update_fields"):
        if "settings_data" in kwargs["update_fields"]:
            estimate_id = instance.id
            pattern = f"oh_ctx:{estimate_id}:*"

            if hasattr(cache, "delete_pattern"):
                cache.delete_pattern(pattern)
            else:
                _increment_cache_version(estimate_id)


def _increment_cache_version(estimate_id: int):
    """
    Инкремент версии кеша для не-Redis бэкендов.

    ВАЖНО: Отключаем сигнал чтобы избежать рекурсии.
    """
    try:
        # Отключаем сигнал на время операции
        post_save.disconnect(
            invalidate_overhead_cache_on_estimate_change, sender=Estimate
        )

        est = Estimate.objects.only("id", "settings_data").get(pk=estimate_id)
        if not est.settings_data:
            est.settings_data = {}

        ver = est.settings_data.get("overhead_cache_version", 0)
        est.settings_data["overhead_cache_version"] = ver + 1
        est.save(update_fields=["settings_data"])

    except Estimate.DoesNotExist:
        pass
    finally:
        # Включаем сигнал обратно
        post_save.connect(invalidate_overhead_cache_on_estimate_change, sender=Estimate)
