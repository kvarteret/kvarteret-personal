from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from app.api.v1.errors import ApiErrorResponse
from app.auth.dependencies import require_authenticated_user
from app.services.courses import CoursesServiceProtocol, get_courses_service

router = APIRouter()


class CourseListItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    course_id: int
    name: str
    description: str | None
    created_at: datetime | None


class RequiredGroupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    group_id: int
    group_name: str


class CourseCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    completion_id: int
    person_id: int
    person_name: str
    completed_semester_code: int
    completed_semester_label: str


class CourseDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    course_id: int
    name: str
    description: str | None
    created_at: datetime | None
    required_groups: list[RequiredGroupResponse]
    recent_completions: list[CourseCompletionResponse]


def _get_courses_service_for_request(request: Request) -> CoursesServiceProtocol:
    if getattr(request.app.state, "courses_service", None) is not None:
        return request.app.state.courses_service
    return get_courses_service()


@router.get("/courses", response_model=list[CourseListItemResponse], responses={503: {"model": ApiErrorResponse}})
async def list_courses(
    request: Request,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    _current_user=Depends(require_authenticated_user),
):
    try:
        courses = await _get_courses_service_for_request(request).list_courses(query=q, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "courses_unavailable", "message": str(exc)},
        ) from exc
    return [CourseListItemResponse.model_validate(course) for course in courses]


@router.get("/courses/{course_id}", response_model=CourseDetailResponse, responses={404: {"model": ApiErrorResponse}})
async def get_course_detail(
    request: Request,
    course_id: int,
    _current_user=Depends(require_authenticated_user),
):
    try:
        course = await _get_courses_service_for_request(request).get_course_detail(course_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "courses_unavailable", "message": str(exc)},
        ) from exc
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "course_not_found", "message": f"Course {course_id} was not found."},
        )
    return CourseDetailResponse.model_validate(course)
