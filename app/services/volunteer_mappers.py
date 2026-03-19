from __future__ import annotations

from app.services.common import build_full_name, coerce_date, coerce_datetime
from app.services.volunteer_models import (
    AssignmentRoleOption,
    CardItem,
    DocumentItem,
    GroupOption,
    NextOfKinItem,
    RoleAssignmentItem,
    VolunteerDetail,
    VolunteerListItem,
    VolunteerRelations,
)
from app.services.volunteer_options import gender_label, normalize_gender_code
from app.services.semester import format_semester_code


def build_document_storage_path(volunteer_id: int, filename: str) -> str:
    return f"{volunteer_id}/{filename}"


def build_photo_url(sha1: str | None, filetype: str | None) -> str | None:
    return None


def build_document_url(volunteer_id: int, filename: str | None) -> str | None:
    return None


def map_volunteer_list_item(row: dict) -> VolunteerListItem:
    last_semester_code = int(row["last_semester"]) if row.get("last_semester") is not None else None
    return VolunteerListItem(
        volunteer_id=row["id"],
        first_name=row["fornavn"],
        last_name=row["etternavn"],
        full_name=build_full_name(row["fornavn"], row["etternavn"]),
        email=row["epost"],
        phone=row["telefon"],
        photo_url=build_photo_url(row.get("sha1"), row.get("filetype")),
        pingvin_points=int(row.get("pingvin_points") or 0),
        last_semester_code=last_semester_code,
        last_semester_label=format_semester_code(last_semester_code),
    )


def map_volunteer_detail(row: dict) -> VolunteerDetail:
    gender_code = normalize_gender_code(row.get("kjonn"))
    return VolunteerDetail(
        volunteer_id=row["id"],
        first_name=row["fornavn"],
        last_name=row["etternavn"],
        full_name=build_full_name(row["fornavn"], row["etternavn"]),
        email=row["epost"],
        phone=row["telefon"],
        birth_date=coerce_date(row.get("fodselsdato")),
        created_at=coerce_datetime(row["opprettet"]),
        gender_code=gender_code,
        gender_label=gender_label(gender_code),
        address=row["gateadresse"],
        postal_code=row["postnummerid"],
        photo_url=build_photo_url(row.get("sha1"), row.get("filetype")),
    )


def map_document_item(volunteer_id: int, row: dict) -> DocumentItem:
    return DocumentItem(
        document_id=int(row["id"]),
        filename=row["filename"],
        filetype=row.get("filetype"),
        group_id=row.get("gruppekobling"),
        created_at=coerce_datetime(row["opprettet"]),
        storage_path=build_document_storage_path(volunteer_id, row["filename"]),
        download_url=build_document_url(volunteer_id, row["filename"]),
    )


def map_role_assignment_item(row: dict) -> RoleAssignmentItem:
    semester_code = int(row["semester"])
    return RoleAssignmentItem(
        history_id=int(row["id"]),
        group_id=int(row["id_gruppe"]),
        group_name=row.get("group_name") or f"Group {row['id_gruppe']}",
        role_id=row.get("id_verv"),
        role_name=row.get("role_name"),
        semester_code=semester_code,
        semester_label=format_semester_code(semester_code) or str(semester_code),
        contract_signed=bool(row["signert_kontrakt"]),
    )


def map_relations(rows: list[dict]) -> VolunteerRelations:
    next_of_kin: list[NextOfKinItem] = []
    cards: list[CardItem] = []
    for row in rows:
        if row["relation_type"] == "kin":
            next_of_kin.append(
                NextOfKinItem(
                    next_of_kin_id=int(row["relation_id"]),
                    name=row["primary_text"],
                    phone=row["secondary_text"],
                )
            )
        elif row["relation_type"] == "card":
            cards.append(
                CardItem(
                    card_id=int(row["relation_id"]),
                    card_number=row["primary_text"],
                )
            )
    return VolunteerRelations(next_of_kin=next_of_kin, cards=cards)


def map_group_option(row: dict) -> GroupOption:
    return GroupOption(
        group_id=int(row["id"]),
        name=row["navn"],
        active=bool(row["aktiv"]),
    )


def map_role_option(row: dict) -> AssignmentRoleOption:
    return AssignmentRoleOption(
        role_id=int(row["id"]),
        group_id=int(row["id_gruppe"]),
        role_name=row["verv"] or "Uten navn",
        pingvin_points=int(row.get("pingvinpoeng") or 0),
    )
