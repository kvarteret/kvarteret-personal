from __future__ import annotations

from app.media_tokens import build_document_media_url, build_photo_media_url
from app.services.common import build_full_name, coerce_date, coerce_datetime
from app.services.people_models import (
    CardItem,
    DocumentItem,
    MembershipItem,
    NextOfKinItem,
    PersonDetailShell,
    PersonListItem,
    PersonRelations,
)
from app.services.semester import format_semester_code


def build_document_storage_path(person_id: int, filename: str) -> str:
    return f"{person_id}/{filename}"


def build_photo_url(sha1: str | None, filetype: str | None) -> str | None:
    if not sha1 or not filetype:
        return None
    return build_photo_media_url(f"{sha1}.{filetype}")


def build_document_url(person_id: int, filename: str | None) -> str | None:
    if not filename:
        return None
    return build_document_media_url(build_document_storage_path(person_id, filename))


def map_person_list_item(row: dict) -> PersonListItem:
    last_semester_code = int(row["last_semester"]) if row.get("last_semester") is not None else None
    return PersonListItem(
        person_id=row["id"],
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


def map_person_detail_shell(row: dict) -> PersonDetailShell:
    return PersonDetailShell(
        person_id=row["id"],
        first_name=row["fornavn"],
        last_name=row["etternavn"],
        full_name=build_full_name(row["fornavn"], row["etternavn"]),
        email=row["epost"],
        phone=row["telefon"],
        birth_date=coerce_date(row.get("fodselsdato")),
        created_at=coerce_datetime(row["opprettet"]),
        gender=row["kjonn"],
        address=row["gateadresse"],
        postal_code=row["postnummerid"],
        employment_status=row["arb_status"],
        photo_url=build_photo_url(row.get("sha1"), row.get("filetype")),
    )


def map_document_item(person_id: int, row: dict) -> DocumentItem:
    return DocumentItem(
        document_id=int(row["id"]),
        filename=row["filename"],
        filetype=row.get("filetype"),
        group_id=row.get("gruppekobling"),
        created_at=coerce_datetime(row["opprettet"]),
        storage_path=build_document_storage_path(person_id, row["filename"]),
        download_url=build_document_url(person_id, row["filename"]),
    )


def map_membership_item(row: dict) -> MembershipItem:
    semester_code = int(row["semester"])
    return MembershipItem(
        history_id=int(row["id"]),
        group_id=int(row["id_gruppe"]),
        group_name=row.get("group_name") or f"Group {row['id_gruppe']}",
        role_id=row.get("id_verv"),
        role_name=row.get("role_name"),
        semester_code=semester_code,
        semester_label=format_semester_code(semester_code) or str(semester_code),
        contract_signed=bool(row["signert_kontrakt"]),
    )


def map_relations(rows: list[dict]) -> PersonRelations:
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
    return PersonRelations(next_of_kin=next_of_kin, cards=cards)
