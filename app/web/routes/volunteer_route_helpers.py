from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.auth.roles import UserRole
from app.services.courses import CoursesService
from app.services.volunteer_models import CardItem, NextOfKinItem
from app.services.semester import get_current_semester_code
from app.services.volunteer_options import SEMESTER_TERM_OPTIONS
from app.services.volunteers import VolunteersService
from app.web.templates import templates


async def render_role_assignments_panel(
    request: Request,
    *,
    current_user,
    volunteers_service: VolunteersService,
    volunteer,
    editing_assignment_id: int | None = None,
):
    assignments = await volunteers_service.list_role_assignments(volunteer.volunteer_id)
    groups = (
        await volunteers_service.list_assignment_groups()
        if current_user.role in {UserRole.ADMIN, UserRole.GROUP_ADMIN}
        else []
    )
    editing_assignment = next(
        (assignment for assignment in assignments if assignment.history_id == editing_assignment_id),
        None,
    )
    editing_role_options = (
        await volunteers_service.list_assignment_roles(editing_assignment.group_id)
        if current_user.role in {UserRole.ADMIN, UserRole.GROUP_ADMIN} and editing_assignment is not None
        else []
    )
    current_semester_code = get_current_semester_code()
    return templates.TemplateResponse(
        request,
        "components/volunteer_role_assignments_panel.html",
        {
            "current_user": current_user,
            "volunteer": volunteer,
            "assignments": assignments,
            "group_options": groups,
            "editing_assignment": editing_assignment,
            "editing_role_options": editing_role_options,
            "semester_term_options": SEMESTER_TERM_OPTIONS,
            "current_semester_code": current_semester_code,
            "has_active_contract": any(
                assignment.semester_code == current_semester_code and assignment.contract_signed
                for assignment in assignments
            ),
        },
    )


async def require_existing_volunteer(
    volunteers_service: VolunteersService,
    volunteer_id: int,
):
    volunteer = await volunteers_service.get_volunteer_detail(volunteer_id)
    if volunteer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Volunteer not found.")
    return volunteer


async def render_relations_panel(
    request: Request,
    *,
    current_user,
    volunteers_service: VolunteersService,
    volunteer,
    editing: bool = False,
):
    relations = await volunteers_service.get_volunteer_relations(volunteer.volunteer_id)
    can_manage_relations = current_user.role in {UserRole.ADMIN, UserRole.GROUP_ADMIN}
    editing_relations = editing and can_manage_relations
    editable_cards = relations.cards if relations.cards else [CardItem(card_id=0, card_number="")]
    editable_next_of_kin = (
        relations.next_of_kin if relations.next_of_kin else [NextOfKinItem(next_of_kin_id=0, name="", phone="")]
    )
    return templates.TemplateResponse(
        request,
        "components/volunteer_relations_panel.html",
        {
            "current_user": current_user,
            "volunteer": volunteer,
            "cards": relations.cards,
            "next_of_kin": relations.next_of_kin,
            "can_manage_relations": can_manage_relations,
            "editing_relations": editing_relations,
            "editable_cards": editable_cards,
            "editable_next_of_kin": editable_next_of_kin,
        },
    )


async def render_course_completions_panel(
    request: Request,
    *,
    current_user,
    volunteers_service: VolunteersService,
    courses_service: CoursesService,
    volunteer,
):
    completions = await volunteers_service.list_course_completions(volunteer.volunteer_id)
    can_manage_course_completions = current_user.role in {UserRole.ADMIN, UserRole.GROUP_ADMIN}
    course_options = (
        await courses_service.list_courses(limit=500)
        if can_manage_course_completions
        else []
    )
    current_semester_code = get_current_semester_code()
    return templates.TemplateResponse(
        request,
        "components/volunteer_course_completions_panel.html",
        {
            "current_user": current_user,
            "volunteer": volunteer,
            "completions": completions,
            "course_options": course_options,
            "can_manage_course_completions": can_manage_course_completions,
            "semester_term_options": SEMESTER_TERM_OPTIONS,
            "default_year": current_semester_code // 10,
            "default_term": current_semester_code % 10,
        },
    )
