from __future__ import annotations
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from .models import ImportedEstimateFile, ParseResult
from .utils import compute_sha256, parse_excel_to_json


def save_imported_file(uploaded: UploadedFile) -> ImportedEstimateFile:
    obj = ImportedEstimateFile.objects.create(
        file=uploaded,
        original_name=uploaded.name,
        size_bytes=getattr(uploaded, "size", 0) or 0,
    )
    f = obj.file.open("rb")
    obj.sha256 = compute_sha256(f)
    obj.save(update_fields=["sha256"])
    return obj


@transaction.atomic
def parse_and_store(file_obj: ImportedEstimateFile) -> ParseResult:
    data = parse_excel_to_json(file_obj.file.path)
    estimate_name = (data.get("extracted", {}) or {}).get("estimate_name", "")[:255]
    pr, _ = ParseResult.objects.update_or_create(
        file=file_obj, defaults={"data": data, "estimate_name": estimate_name}
    )
    return pr
