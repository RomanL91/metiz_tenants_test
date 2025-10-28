from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django.utils.translation import gettext_lazy as _

from .serializers import (
    MaterialImportFileSerializer,
    MaterialImportResultSerializer,
)
from .services import MaterialImportService
from .exceptions import (
    MaterialImportException,
    InvalidFileFormatException,
    InvalidFileStructureException,
    FileProcessingException,
)


class MaterialImportViewSet(APIView):
    """API для импорта материалов из Excel"""

    permission_classes = [IsAuthenticated]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.import_service = MaterialImportService()

    @extend_schema(
        summary=_("Импорт материалов из Excel"),
        description=_(
            "Загрузка и импорт материалов из Excel файла (.xlsx, .xls). "
            "Файл должен содержать обязательные колонки: Наименование, "
            "Единица измерения, Цена. Опциональные: Поставщик, НДС %."
        ),
        request=MaterialImportFileSerializer,
        responses={
            200: OpenApiResponse(
                response=MaterialImportResultSerializer,
                description=_("Успешный импорт"),
            ),
            400: OpenApiResponse(
                description=_("Ошибка валидации файла или данных"),
            ),
            500: OpenApiResponse(
                description=_("Внутренняя ошибка сервера"),
            ),
        },
        tags=["Материалы"],
    )
    def post(self, request):
        """Импорт материалов из файла"""
        serializer = MaterialImportFileSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": _("Ошибка валидации файла"),
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        file = serializer.validated_data["file"]

        try:
            result = self.import_service.import_materials(file)

            result_serializer = MaterialImportResultSerializer(data=result.to_dict())
            result_serializer.is_valid(raise_exception=True)

            return Response(
                result_serializer.data,
                status=status.HTTP_200_OK,
            )

        except InvalidFileFormatException as e:
            return Response(
                {
                    "status": "error",
                    "message": str(e),
                    "errors": [],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except InvalidFileStructureException as e:
            return Response(
                {
                    "status": "error",
                    "message": str(e),
                    "errors": [],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except FileProcessingException as e:
            return Response(
                {
                    "status": "error",
                    "message": str(e),
                    "errors": [],
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        except MaterialImportException as e:
            return Response(
                {
                    "status": "error",
                    "message": str(e),
                    "errors": [],
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
