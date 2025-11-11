from django.db import transaction
from app_outlay.models import Estimate, Group, GroupTechnicalCardLink
from app_technical_cards.models import (
    TechnicalCard,
    TechnicalCardVersion,
    TechnicalCardVersionMaterial,
    TechnicalCardVersionWork,
)
from app_materials.models import Material
from app_works.models import Work


@transaction.atomic
def materialize_estimate_from_markup(markup, sheet_index: int = 0) -> Estimate:

    pr = markup.parse_result
    estimate_name = pr.estimate_name or markup.file.original_name
    estimate = Estimate.objects.create(name=estimate_name)

    estimate.source_file = markup.file  # ImportedEstimateFile
    estimate.source_sheet_index = sheet_index  # если есть понимание листа; иначе 0
    estimate.save(update_fields=["source_file", "source_sheet_index"])

    # построим кэш групп по пути

    if not Group.objects.filter(estimate=estimate).exists():
        Group.objects.get_or_create(
            estimate=estimate,
            parent=None,
            defaults={"name": "Общий раздел", "order": 0},
        )
    group_cache: dict[tuple[str, ...], Group] = {}

    def ensure_group_path(path: tuple[str, ...]) -> Group:
        if path in group_cache:
            return group_cache[path]
        parent = None
        built = []
        for depth, title in enumerate(path, start=1):
            key = tuple(path[:depth])
            if key in group_cache:
                parent = group_cache[key]
                continue
            g = Group.objects.create(
                estimate=estimate, name=title, parent=parent, order=depth
            )
            group_cache[key] = g
            parent = g
            built.append(g)
        return parent or Group.objects.create(
            estimate=estimate, name=estimate_name, parent=None, order=0
        )

    uid_to_title = _index_titles_by_uid(pr.data, markup.annotation)
    ann = markup.annotation or {}
    labels: dict = ann.get("labels") or {}
    tech_list: list[dict] = ann.get("tech_cards") or []
    schema = (ann.get("schema") or {}).get("col_roles") or []

    # восстановим пути групп из labels: берём только names uid с префиксом наших генераторов
    # (в build_annotation_from_grid они "s0-G{depth}-hash")
    def group_path_for_tc(tc_uid: str) -> tuple[str, ...]:
        # эвристика: нет явной привязки uid→path; используем «sticky» сформированный по ходу извлечения — для простоты возьмём все G* в names в порядке depth
        names = ann.get("names") or {}
        path = []
        for depth in range(1, 7):
            # берём все соответствующие G{depth}
            candidates = [
                names[u] for u in names.keys() if u.startswith(f"s0-G{depth}-")
            ]
            # выбираем любой (или игнорируем) — для простоты пропустим если их много
            if len(candidates) == 1:
                path.append(candidates[0])
        return tuple(path)

    order = 0
    for tc in tech_list:
        tcu = tc.get("uid")
        tc_title = uid_to_title.get(tcu, tcu)
        head, _ = TechnicalCard.objects.get_or_create(name=tc_title)
        last = head.versions.order_by("-version").first()
        ver = (last.version + 1) if last else 1
        tcv = TechnicalCardVersion.objects.create(
            card=head, version=ver, name=head.name
        )

        for w in tc.get("works") or []:
            w_title = uid_to_title.get(w, w)
            work, _ = Work.objects.get_or_create(name=w_title)
            TechnicalCardVersionWork.objects.create(
                technical_card_version=tcv, work=work, work_name=work.name
            )

        for m in tc.get("materials") or []:
            m_title = uid_to_title.get(m, m)
            mat, _ = Material.objects.get_or_create(name=m_title)
            TechnicalCardVersionMaterial.objects.create(
                technical_card_version=tcv, material=mat, material_name=mat.name
            )

        # группа для ТК
        gpath = group_path_for_tc(tcu)
        group = ensure_group_path(gpath)
        GroupTechnicalCardLink.objects.create(
            group=group, technical_card_version=tcv, order=order
        )
        order += 1

    return estimate


def _index_titles_by_uid(
    data: dict, markup_annotation: dict | None = None
) -> dict[str, str]:
    out: dict[str, str] = {}
    # из blocks (если были)
    for sheet in data.get("sheets") or []:
        for b in sheet.get("blocks") or []:
            _collect_titles(b, out)
    # из names внутри аннотации (грид-режим)
    names = (markup_annotation or {}).get("names") or {}
    for uid, title in names.items():
        out.setdefault(uid, title)
    return out


def _collect_titles(node: dict, out: dict):
    uid = node.get("uid")
    title = node.get("title") or ""
    if uid and title:
        out[uid] = title
    for ch in node.get("children") or []:
        _collect_titles(ch, out)
