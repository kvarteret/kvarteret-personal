from __future__ import annotations

from app.shared.coercion import coerce_date, require_datetime
from app.shared.text import build_full_name
from app.domain.volunteers.models import (
    AssignmentRoleOption,
    CardItem,
    GroupOption,
    NextOfKinItem,
    RoleAssignmentItem,
    VolunteerCourseCompletionItem,
    VolunteerDetail,
    VolunteerListItem,
    VolunteerRegistrationLogEntry,
    VolunteerRelations,
)
from app.domain.volunteers.options import gender_label, normalize_gender_code
from app.infrastructure.formatting.semester import format_semester_code


def map_volunteer_list_item(row: dict) -> VolunteerListItem:
    last_semester_code = (
        int(row["last_semester"]) if row.get("last_semester") is not None else None
    )
    return VolunteerListItem(
        volunteer_id=row["id"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        full_name=build_full_name(row["first_name"], row["last_name"]),
        email=row["email"],
        phone=row["phone"],
        photo_url=None,
        pingvin_points=int(row.get("pingvin_points") or 0),
        last_semester_code=last_semester_code,
        last_semester_label=format_semester_code(last_semester_code),
    )


def map_volunteer_detail(row: dict) -> VolunteerDetail:
    gender_code = normalize_gender_code(row.get("gender"))
    return VolunteerDetail(
        volunteer_id=row["id"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        full_name=build_full_name(row["first_name"], row["last_name"]),
        email=row["email"],
        phone=row["phone"],
        birth_date=coerce_date(row.get("birth_date")),
        created_at=require_datetime(row["created_at"]),
        gender_code=gender_code,
        gender_label=gender_label(gender_code),
        address=row["street_address"],
        postal_code=row["postal_code"],
        pingvin_points=int(row.get("pingvin_points") or 0),
        photo_url=None,
        current_discount_level=int(row["current_discount_level"])
        if row.get("current_discount_level") is not None
        else None,
        registration_log_entry=(
            VolunteerRegistrationLogEntry(
                registration_id=int(row["registration_id"]),
                created_at=require_datetime(row["registration_created_at"]),
                source=row["registration_source"],
                status=row["registration_status"],
                first_choice_group_name=row.get("first_choice_group_name"),
                second_choice_group_name=row.get("second_choice_group_name"),
                group_id=row.get("registration_group_id"),
                group_role=row.get("registration_group_role"),
                group_status=row.get("registration_group_status"),
            )
            if row.get("registration_id") is not None
            else None
        ),
    )


def map_role_assignment_item(row: dict) -> RoleAssignmentItem:
    semester_code = int(row["semester"])
    return RoleAssignmentItem(
        history_id=int(row["id"]),
        group_id=int(row["group_id"]),
        group_name=row.get("group_name") or f"Group {row['group_id']}",
        role_id=row.get("role_id"),
        role_name=row.get("role_name"),
        pingvin_points=int(row.get("penguin_points") or 0),
        semester_code=semester_code,
        semester_label=format_semester_code(semester_code) or str(semester_code),
        contract_signed=bool(row["contract_signed"]),
    )


def map_course_completion_item(row: dict) -> VolunteerCourseCompletionItem:
    semester_code = int(row["completed_semester"])
    return VolunteerCourseCompletionItem(
        completion_id=int(row["id"]),
        course_id=int(row["course_id"]),
        course_name=row["course_name"],
        completed_semester_code=semester_code,
        completed_semester_label=format_semester_code(semester_code)
        or str(semester_code),
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
        name=row["name"],
        active=bool(row["is_active"]),
    )


def map_role_option(row: dict) -> AssignmentRoleOption:
    return AssignmentRoleOption(
        role_id=int(row["id"]),
        group_id=int(row["group_id"]),
        role_name=row["name"] or "Uten navn",
        pingvin_points=int(row.get("penguin_points") or 0),
    )
