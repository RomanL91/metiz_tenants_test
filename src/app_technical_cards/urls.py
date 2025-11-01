from django.urls import path
from app_technical_cards.views import (
    TechnicalCardLiveCompositionView,
    TechnicalCardSaveNewVersionView,
    TechnicalCardSearchMaterialsView,
    TechnicalCardSearchWorksView,
    SaveNewVersionApiView,
    LiveCompositionApiView,
)

app_name = "app_technical_cards"

urlpatterns = [
    # ВНИМАНИЕ: без "api/v1/" — этот префикс добавляем в core/urls.py через include()
    path(
        "technical-cards/<int:pk>/live-composition/",
        LiveCompositionApiView.as_view(),
        name="tc-live-composition",
    ),
    path(
        "technical-cards/<int:pk>/save-new-version/",
        SaveNewVersionApiView.as_view(),
        name="tc-save-new-version",
    ),
    path(
        "technical-cards/search/materials/",
        TechnicalCardSearchMaterialsView.as_view(),
        name="tc-search-materials",
    ),
    path(
        "technical-cards/search/works/",
        TechnicalCardSearchWorksView.as_view(),
        name="tc-search-works",
    ),
]
