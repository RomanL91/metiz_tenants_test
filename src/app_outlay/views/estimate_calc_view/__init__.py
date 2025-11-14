"""
Модуль расчёта технических карт в контексте сметы.

Публичный API модуля:
- EstimateCalcAPIView - контроллер для API


Архитектура:
    views.py          → Thin Controllers (обработка HTTP)
    serializers.py    → Валидация данных
    services.py       → Бизнес-логика

Принципы:
- SOLID (особенно Single Responsibility и Dependency Inversion)
- DRY (переиспользование через сервисы и репозитории)
- KISS (простота через паттерны Facade и Repository)

Паттерны:
- Repository Pattern (repositories.py)
- Service Layer Pattern (services.py)
- Facade Pattern (EstimateCalculationFacade)
- Dependency Injection (конструкторы сервисов)

Оптимизации:
- N+1 Prevention (select_related, prefetch_related в репозиториях)
- LRU Cache (кеширование контекста НР)
- Query Optimization (только нужные поля через .only())
"""

from .services import (EstimateCalculationFacade, OverheadContextService,
                       TechnicalCardCalculationService)
from .views import EstimateCalcAPIView

__all__ = [
    # View
    "EstimateCalcAPIView",
    # Services
    "EstimateCalculationFacade",
    "OverheadContextService",
    "TechnicalCardCalculationService",
]
