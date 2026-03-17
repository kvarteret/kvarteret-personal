from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status

from app.dependencies import get_courses_service, require_admin_user
from app.services.courses import CourseDeleteBlockedError, CoursesService
from app.web.route_helpers import blocked_http_exception, log_and_redirect

router = APIRouter()


@router.post("/courses")
async def courses_create(
    request: Request,
    name: str = Form(...),
    description: str | None = Form(default=None),
    current_user=Depends(require_admin_user),
    courses_service: CoursesService = Depends(get_courses_service),
):
    course_id = await courses_service.create_course(name=name, description=description)
    return log_and_redirect(
        request=request,
        user=current_user,
        action="course.create",
        subject_type="course",
        subject_id=course_id,
        redirect_path=f"/courses/{course_id}",
    )


@router.patch("/courses/{course_id}")
async def courses_update(
    request: Request,
    course_id: int,
    name: str = Form(...),
    description: str | None = Form(default=None),
    current_user=Depends(require_admin_user),
    courses_service: CoursesService = Depends(get_courses_service),
):
    updated = await courses_service.update_course(course_id, name=name, description=description)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
    return log_and_redirect(
        request=request,
        user=current_user,
        action="course.update",
        subject_type="course",
        subject_id=course_id,
        redirect_path=f"/courses/{course_id}",
    )


@router.delete("/courses/{course_id}")
async def courses_delete(
    request: Request,
    course_id: int,
    current_user=Depends(require_admin_user),
    courses_service: CoursesService = Depends(get_courses_service),
):
    try:
        deleted = await courses_service.delete_course(course_id)
    except CourseDeleteBlockedError as exc:
        raise blocked_http_exception(exc.blockers) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
    return log_and_redirect(
        request=request,
        user=current_user,
        action="course.delete",
        subject_type="course",
        subject_id=course_id,
        redirect_path="/courses",
    )
