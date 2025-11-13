"""
Базовый репозиторий для работы с данными.

Предоставляет общие методы доступа к данным и снижает связанность
между бизнес-логикой и моделями Django ORM.

Принципы:
- Single Responsibility: только доступ к данным
- Dependency Inversion: бизнес-логика зависит от абстракции, а не от ORM
- Reusability: общие методы для всех репозиториев
"""

from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from django.db.models import Model, QuerySet

ModelType = TypeVar("ModelType", bound=Model)


class BaseRepository(Generic[ModelType]):
    """
    Базовый класс репозитория для работы с Django ORM.

    Использует Generic для типизации модели.

    Example:
        class EstimateRepository(BaseRepository[Estimate]):
            model = Estimate

            def get_with_groups(self, estimate_id: int) -> Estimate:
                return self.get_by_id(estimate_id, prefetch_related=['groups'])
    """

    model: Type[ModelType] = None

    def __init__(self):
        if self.model is None:
            raise ValueError(
                f"{self.__class__.__name__} должен определить атрибут 'model'"
            )

    def get_by_id(
        self,
        obj_id: int,
        select_related: Optional[List[str]] = None,
        prefetch_related: Optional[List[str]] = None,
    ) -> Optional[ModelType]:
        """
        Получить объект по ID с оптимизацией запросов.

        Args:
            obj_id: ID объекта
            select_related: Список связей для select_related
            prefetch_related: Список связей для prefetch_related

        Returns:
            Объект модели или None
        """
        qs = self.model.objects.all()

        if select_related:
            qs = qs.select_related(*select_related)

        if prefetch_related:
            qs = qs.prefetch_related(*prefetch_related)

        return qs.filter(pk=obj_id).first()

    def get_queryset(
        self,
        filters: Optional[Dict[str, Any]] = None,
        select_related: Optional[List[str]] = None,
        prefetch_related: Optional[List[str]] = None,
        order_by: Optional[List[str]] = None,
    ) -> QuerySet[ModelType]:
        """
        Получить QuerySet с фильтрацией и оптимизацией.

        Args:
            filters: Словарь фильтров для QuerySet.filter(**filters)
            select_related: Список связей для select_related
            prefetch_related: Список связей для prefetch_related
            order_by: Список полей для сортировки

        Returns:
            QuerySet модели
        """
        qs = self.model.objects.all()

        if filters:
            qs = qs.filter(**filters)

        if select_related:
            qs = qs.select_related(*select_related)

        if prefetch_related:
            qs = qs.prefetch_related(*prefetch_related)

        if order_by:
            qs = qs.order_by(*order_by)

        return qs

    def exists(self, **filters) -> bool:
        """
        Проверить существование объекта по фильтрам.

        Args:
            **filters: Фильтры для QuerySet.filter()

        Returns:
            True если объект существует
        """
        return self.model.objects.filter(**filters).exists()

    def count(self, **filters) -> int:
        """
        Подсчитать количество объектов по фильтрам.

        Args:
            **filters: Фильтры для QuerySet.filter()

        Returns:
            Количество объектов
        """
        return self.model.objects.filter(**filters).count()

    def create(self, **fields) -> ModelType:
        """
        Создать объект.

        Args:
            **fields: Поля объекта

        Returns:
            Созданный объект
        """
        return self.model.objects.create(**fields)

    def bulk_create(self, instances: List[ModelType]) -> List[ModelType]:
        """
        Массовое создание объектов.

        Args:
            instances: Список экземпляров модели

        Returns:
            Список созданных объектов
        """
        return self.model.objects.bulk_create(instances)

    def update(self, obj_id: int, **fields) -> bool:
        """
        Обновить объект по ID.

        Args:
            obj_id: ID объекта
            **fields: Поля для обновления

        Returns:
            True если объект был обновлён
        """
        updated = self.model.objects.filter(pk=obj_id).update(**fields)
        return updated > 0

    def delete(self, obj_id: int) -> bool:
        """
        Удалить объект по ID.

        Args:
            obj_id: ID объекта

        Returns:
            True если объект был удалён
        """
        deleted, _ = self.model.objects.filter(pk=obj_id).delete()
        return deleted > 0
