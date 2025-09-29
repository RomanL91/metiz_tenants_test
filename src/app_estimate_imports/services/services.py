from __future__ import annotations

import hashlib

from typing import BinaryIO

from openpyxl import load_workbook

from django.db import transaction
from django.core.files.uploadedfile import UploadedFile

from app_estimate_imports.models import ImportedEstimateFile, ParseResult


def compute_sha256(fobj: BinaryIO) -> str:
    h = hashlib.sha256()
    for chunk in iter(lambda: fobj.read(8192), b""):
        h.update(chunk)
    fobj.seek(0)
    return h.hexdigest()


def parse_excel_to_json(path: str) -> dict:
    """
    МИНИМАЛЬНО: читаем имена листов и первые 50 строк в виде текста.
    Дальше усложним, когда определим эвристики/ML.
    """
    wb = load_workbook(filename=path, read_only=True, data_only=True)
    result = {
        "file": {"path": path, "sheets": wb.worksheets.__len__()},
        "sheets": [],
        "extracted": {"estimate_name": ""},
    }
    for ws in wb.worksheets:
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= 50:
                break
            cells = [str(v) if v is not None else "" for v in row]
            rows.append({"row_index": i + 1, "cells": cells})
        result["sheets"].append({"name": ws.title, "rows": rows})
    return result


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
