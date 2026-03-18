from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.auth.roles import UserRole
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
    groups = await volunteers_service.list_assignment_groups() if current_user.role == UserRole.ADMIN else []
    editing_assignment = next(
        (assignment for assignment in assignments if assignment.history_id == editing_assignment_id),
        None,
    )
    selected_group_id = editing_assignment.group_id if editing_assignment is not None else None
    role_options = (
        await volunteers_service.list_assignment_roles(selected_group_id)
        if current_user.role == UserRole.ADMIN and selected_group_id is not None
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
            "selected_group_id": selected_group_id,
            "selected_role_id": editing_assignment.role_id if editing_assignment is not None else None,
            "role_options": role_options,
            "semester_term_options": SEMESTER_TERM_OPTIONS,
            "default_year": editing_assignment.semester_code // 10 if editing_assignment is not None else current_semester_code // 10,
            "default_term": editing_assignment.semester_code % 10 if editing_assignment is not None else current_semester_code % 10,
            "default_contract_signed": editing_assignment.contract_signed if editing_assignment is not None else False,
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
