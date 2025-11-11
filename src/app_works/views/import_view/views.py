from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django.utils.translation import gettext_lazy as _

from .serializers import (
    WorkImportFileSerializer,
    WorkImportResultSerializer,
)
from .services import WorkImportService
from .exceptions import (
    WorkImportException,
    InvalidFileFormatException,
    InvalidFileStructureException,
    FileProcessingException,
)


class WorkImportViewSet(APIView):
    """API для импорта работ из Excel"""

    permission_classes = [IsAuthenticated]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.import_service = WorkImportService()

    @extend_schema(
        summary=_("Импорт работ из Excel"),
        description=_(
            "Загрузка и импорт работ из Excel файла (.xlsx, .xls). "
            "Файл должен содержать обязательные колонки: Наименование, "
            "Единица измерения, Цена."
        ),
        request=WorkImportFileSerializer,
        responses={
            200: OpenApiResponse(
                response=WorkImportResultSerializer,
                description=_("Успешный импорт"),
            ),
            400: OpenApiResponse(
                description=_("Ошибка валидации файла или данных"),
            ),
            500: OpenApiResponse(
                description=_("Внутренняя ошибка сервера"),
            ),
        },
        tags=["Работы"],
    )
    def post(self, request):
        serializer = WorkImportFileSerializer(data=request.data)

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
            result = self.import_service.import_works(file)

            result_serializer = WorkImportResultSerializer(data=result.to_dict())
            result_serializer.is_valid(raise_exception=True)

            return Response(result_serializer.data, status=status.HTTP_200_OK)

        except InvalidFileFormatException as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "errors": [],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except InvalidFileStructureException as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "errors": [],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except FileProcessingException as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "errors": [],
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except WorkImportException as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "errors": [],
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
