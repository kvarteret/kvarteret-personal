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
):
    assignments = await volunteers_service.list_role_assignments(volunteer.volunteer_id)
    groups = await volunteers_service.list_assignment_groups() if current_user.role == UserRole.ADMIN else []
    current_semester_code = get_current_semester_code()
    return templates.TemplateResponse(
        request,
        "components/volunteer_role_assignments_panel.html",
        {
            "current_user": current_user,
            "volunteer": volunteer,
            "assignments": assignments,
            "group_options": groups,
            "selected_group_id": None,
            "role_options": [],
            "semester_term_options": SEMESTER_TERM_OPTIONS,
            "default_year": current_semester_code // 10,
            "default_term": current_semester_code % 10,
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
