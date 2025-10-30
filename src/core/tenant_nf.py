from django.http import JsonResponse


def tenant_not_found(request):
    from django.db import connection

    info = {
        "where": "TENANT_NOT_FOUND_VIEW",
        # "HTTP_HOST": request.META.get("HTTP_HOST"),
        # "X-Forwarded-Host": request.META.get("HTTP_X_FORWARDED_HOST"),
        # "get_host()": request.get_host(),
        # "path": request.path,
        # "schema": getattr(connection, "schema_name", "?"),
    }
    return JsonResponse(info, status=404, json_dumps_params={"ensure_ascii": False})
