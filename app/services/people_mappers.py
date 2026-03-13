from __future__ import annotations

from app.media_tokens import build_document_media_url, build_photo_media_url
from app.services.common import build_full_name, coerce_date, coerce_datetime
from app.services.people_models import (
    CardItem,
    DocumentItem,
    MembershipItem,
    NextOfKinItem,
    PersonDetail,
    PersonListItem,
)
from app.services.semester import format_semester_code


def build_document_storage_path(person_id: int, filename: str) -> str:
    return f"{person_id}/{filename}"


def build_photo_url_from_embedded(bilde_data) -> str | None:
    if not bilde_data:
        return None
    if isinstance(bilde_data, list):
        bilde_data = bilde_data[0] if bilde_data else None
    if not bilde_data:
        return None
    sha1 = bilde_data.get("sha1")
    filetype = bilde_data.get("filetype")
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
        birth_date=coerce_date(row.get("fodselsdato")),
        created_at=coerce_datetime(row["opprettet"]),
        photo_url=build_photo_url_from_embedded(row.get("personal_bilde")),
        pingvin_points=int(row.get("pingvin_points") or 0),
        last_semester_code=last_semester_code,
        last_semester_label=format_semester_code(last_semester_code),
    )


def map_search_person_list_item(row: dict) -> PersonListItem:
    last_semester_code = int(row["last_semester"]) if row.get("last_semester") is not None else None
    return PersonListItem(
        person_id=row["id"],
        first_name=row["fornavn"],
        last_name=row["etternavn"],
        full_name=build_full_name(row["fornavn"], row["etternavn"]),
        email=row["epost"],
        phone=row["telefon"],
        birth_date=coerce_date(row.get("fodselsdato")),
        created_at=coerce_datetime(row["opprettet"]),
        photo_url=build_photo_url_from_embedded(
            {"sha1": row["sha1"], "filetype": row["filetype"]} if row["sha1"] and row["filetype"] else None
        ),
        pingvin_points=int(row.get("pingvin_points") or 0),
        last_semester_code=last_semester_code,
        last_semester_label=format_semester_code(last_semester_code),
    )


def map_person_detail(row: dict) -> PersonDetail:
    person_id = row["id"]
    created_at = coerce_datetime(row["opprettet"])
    memberships_raw = sorted(
        row.get("historie") or [],
        key=lambda membership: (membership.get("semester", 0), membership.get("id", 0)),
        reverse=True,
    )[:12]
    return PersonDetail(
        person_id=person_id,
        first_name=row["fornavn"],
        last_name=row["etternavn"],
        full_name=build_full_name(row["fornavn"], row["etternavn"]),
        email=row["epost"],
        phone=row["telefon"],
        birth_date=coerce_date(row.get("fodselsdato")),
        created_at=created_at,
        gender=row["kjonn"],
        address=row["gateadresse"],
        postal_code=row["postnummerid"],
        employment_status=row["arb_status"],
        photo_url=build_photo_url_from_embedded(row.get("personal_bilde")),
        documents=[
            DocumentItem(
                document_id=int(item["id"]),
                filename=item["filename"],
                filetype=item.get("filetype"),
                group_id=item.get("gruppekobling"),
                created_at=coerce_datetime(item.get("opprettet")) or created_at,
                storage_path=build_document_storage_path(person_id, item["filename"]),
                download_url=build_document_url(person_id, item["filename"]),
            )
            for item in sorted(
                row.get("personal_fil") or [],
                key=lambda item: (item.get("opprettet") or "", item.get("id", 0)),
                reverse=True,
            )
        ],
        next_of_kin=[
            NextOfKinItem(
                next_of_kin_id=int(item["id"]),
                name=item["navn"],
                phone=item["telefon"],
            )
            for item in sorted(
                row.get("paarorende") or [],
                key=lambda item: (item.get("opprettet") or "", item.get("id", 0)),
                reverse=True,
            )
        ],
        cards=[
            CardItem(
                card_id=int(item["id"]),
                card_number=item["kortnummer"],
            )
            for item in sorted(
                row.get("personal_kort") or [],
                key=lambda item: (item.get("opprettet") or "", item.get("id", 0)),
                reverse=True,
            )
        ],
        recent_memberships=[
            MembershipItem(
                history_id=int(item["id"]),
                group_id=int(item["id_gruppe"]),
                group_name=(item.get("grupper") or {}).get("navn") or f"Group {item['id_gruppe']}",
                role_id=item.get("id_verv"),
                role_name=(item.get("verv") or {}).get("verv"),
                semester_code=int(item["semester"]),
                semester_label=format_semester_code(int(item["semester"])) or str(item["semester"]),
                contract_signed=bool(item["signert_kontrakt"]),
            )
            for item in memberships_raw
        ],
    )
