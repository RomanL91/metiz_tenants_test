# Модуль расчёта технических карт в контексте сметы

## Описание

Модуль предоставляет API для расчёта показателей технических карт с учётом накладных расходов сметы.

## Архитектура

```
estimate_calc_view/
├── __init__.py           # Публичный API модуля
├── views.py              # Контроллеры (Thin Controllers)
├── serializers.py        # Валидация входных данных (DRF Serializers)
├── services.py           # Бизнес-логика (Service Layer)

```

## Принципы проектирования

### SOLID

- **S**ingle Responsibility: каждый модуль отвечает за одну задачу
- **O**pen/Closed: расширение через наследование (BaseRepository)
- **L**iskov Substitution: репозитории взаимозаменяемы
- **I**nterface Segregation: сервисы имеют чёткие интерфейсы
- **D**ependency Inversion: зависимости через Dependency Injection

### Паттерны

- **Repository Pattern**: изоляция доступа к данным
- **Service Layer**: бизнес-логика отдельно от контроллеров
- **Facade Pattern**: упрощение взаимодействия (EstimateCalculationFacade)
- **Dependency Injection**: гибкость и тестируемость

## API Endpoint

### GET /api/estimate/{estimate_id}/calc/

Расчёт показателей ТК с учётом НР сметы.

**Query Parameters:**
- `tc` (required): ID технической карты
- `qty` (required): Количество (поддерживает запятую и точку)

**Response:**
```json
{
    "ok": true,
    "calc": {
        "UNIT_PRICE_OF_MATERIAL": 150.50,
        "UNIT_PRICE_OF_WORK": 200.00,
        "TOTAL_PRICE": 3505.00
    },
    "order": ["UNIT_PRICE_OF_MATERIAL", ...]
}
```

**Errors:**
- `400` - Некорректные параметры
- `404` - Смета или ТК не найдена
- `500` - Внутренняя ошибка

## Использование

### В admin.py

```python
from .views.estimate_calc_view.urls import urlpatterns as calc_urls

class EstimateAdmin(admin.ModelAdmin):
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("<path:object_id>/api/", include(calc_urls)),
        ]
        return custom + urls
```

### Программное использование

```python
from .views.estimate_calc_view import EstimateCalculationFacade

facade = EstimateCalculationFacade()
calc, order = facade.calculate_tc_for_estimate(
    estimate_id=1,
    tc_id=123,
    quantity=10.5
)
```

## Оптимизации

### N+1 Prevention

Репозитории используют `select_related` и `prefetch_related`:

```python
def get_overhead_links(self, estimate):
    return EstimateOverheadCostLink.objects.filter(
        estimate=estimate, is_active=True
    ).select_related("overhead_cost_container")  # ← Избегаем N+1
```

### LRU Cache

Контекст НР кешируется в памяти:

```python
@lru_cache(maxsize=100)
def _calculate_context_cached(self, estimate_id):
    # Кеш инвалидируется при изменении estimate_id
    ...
```

Сброс кеша вручную:

```python
from .views.estimate_calc_view import OverheadContextService

OverheadContextService.clear_cache()
```

## Зависимости

- Django REST Framework
- drf-spectacular (для документации API)
- app_outlay.models (Estimate, EstimateOverheadCostLink, etc)
- app_outlay.utils_calc (основная логика расчётов)
- app_technical_cards.models (TechnicalCard, TechnicalCardVersion)

## Миграция из admin.py

**Было:**
```python
# admin.py (строки 478-562)
def api_calc(self, request, object_id):
    # 85 строк монолитного кода
    ...
```

**Стало:**
```python
# views/estimate_calc_view/views.py
class EstimateCalcAPIView(APIView):
    def get(self, request, estimate_id):
        # 20 строк тонкого контроллера
        calc, order = self.calc_facade.calculate_tc_for_estimate(...)
```

**Преимущества:**
- ✅ Разделение ответственности (view → service → repository)
- ✅ Переиспользуемость (EstimateCalculationFacade)
- ✅ Тестируемость (Dependency Injection)
- ✅ Оптимизация (LRU cache, N+1 prevention)
- ✅ Документация (DRF Spectacular)