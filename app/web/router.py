import asyncio
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.cookies import sign_session_id, unsign_session_id
from app.auth.dependencies import require_authenticated_user
from app.auth.login_service import LoginError, get_login_service
from app.auth.roles import UserRole
from app.services.courses import get_courses_service
from app.services.groups import get_groups_service
from app.services.people import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    PersonNotFoundError,
    UnsupportedUploadError,
    get_people_service,
)
from app.services.registrations import (
    RegistrationConflictError,
    RegistrationNotFoundError,
    RegistrationSubmissionInput,
    get_registrations_service,
)
from app.services.search import SearchFilterList, SearchQuery, get_search_service
from app.services.semester_transfer import SemesterTransferEntry, get_semester_transfer_service
from app.services.users import get_users_service

templates = Jinja2Templates(directory="app/templates")

web_router = APIRouter()
PEOPLE_PAGE_SIZE = 10


def _get_login_service_for_request(request: Request):
    if request.app.state.login_service is not None:
        return request.app.state.login_service
    return get_login_service()


def _get_people_service_for_request(request: Request):
    if request.app.state.people_service is not None:
        return request.app.state.people_service
    return get_people_service()


def _get_groups_service_for_request(request: Request):
    if request.app.state.groups_service is not None:
        return request.app.state.groups_service
    return get_groups_service()


def _get_courses_service_for_request(request: Request):
    if request.app.state.courses_service is not None:
        return request.app.state.courses_service
    return get_courses_service()


def _get_search_service_for_request(request: Request):
    if request.app.state.search_service is not None:
        return request.app.state.search_service
    return get_search_service()


def _get_users_service_for_request(request: Request):
    if request.app.state.users_service is not None:
        return request.app.state.users_service
    return get_users_service()


def _get_registrations_service_for_request(request: Request):
    if getattr(request.app.state, "registrations_service", None) is not None:
        return request.app.state.registrations_service
    return get_registrations_service()


def _get_semester_transfer_service_for_request(request: Request):
    if getattr(request.app.state, "semester_transfer_service", None) is not None:
        return request.app.state.semester_transfer_service
    return get_semester_transfer_service()


def _require_admin(current_user):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is required.")
    return current_user


@web_router.get("/")
async def dashboard(request: Request):
    if getattr(request.state, "current_user", None) is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "pages/dashboard.html",
        {
            "title": "Kvarteret Personal",
            "section": "dashboard",
            "current_user": request.state.current_user,
        },
    )


@web_router.get("/login")
async def login(request: Request):
    if getattr(request.state, "current_user", None) is not None:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "pages/login.html",
        {
            "title": "Login",
            "section": "login",
            "error_message": None,
        },
    )


@web_router.post("/login")
async def login_submit(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
):
    try:
        result = await _get_login_service_for_request(request).login_with_bridge(
            identifier=identifier,
            password=password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except RuntimeError:
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {
                "title": "Login",
                "section": "login",
                "error_message": "Login is not configured yet.",
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except LoginError:
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {
                "title": "Login",
                "section": "login",
                "error_message": "Invalid credentials.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=request.app.state.settings.session_cookie_name,
        value=sign_session_id(result.session.session_id),
        httponly=True,
        secure=request.url.scheme == "https" or request.app.state.settings.app_env == "production",
        samesite="lax",
        max_age=request.app.state.settings.session_ttl_hours * 3600,
    )
    return response


@web_router.post("/logout")
async def logout(request: Request):
    cookie_name = request.app.state.settings.session_cookie_name
    signed_cookie = request.cookies.get(cookie_name)
    if signed_cookie:
        try:
            session_id = unsign_session_id(signed_cookie)
            await request.app.state.session_store.delete_session(session_id)
        except Exception:
            pass
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(cookie_name)
    return response


@web_router.get("/people")
async def people_index(
    request: Request,
    q: str | None = None,
    offset: int = 0,
    current_user=Depends(require_authenticated_user),
):
    try:
        page = await _get_people_service_for_request(request).list_people_page(
            query=q,
            limit=PEOPLE_PAGE_SIZE,
            offset=offset,
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed people views are not configured yet.",
        )
    context = {
        "title": "People",
        "section": "people",
        "current_user": current_user,
        "people": page.items,
        "query": q or "",
        "offset": max(0, offset),
        "next_offset": page.next_offset,
    }
    if request.headers.get("HX-Request") == "true" and request.headers.get("HX-Boosted") is None:
        return templates.TemplateResponse(
            request,
            "components/people_results.html",
            context,
        )
    return templates.TemplateResponse(
        request,
        "pages/people.html",
        context,
    )


@web_router.get("/people/{person_id}")
async def people_detail(request: Request, person_id: int, current_user=Depends(require_authenticated_user)):
    try:
        person = await _get_people_service_for_request(request).get_person_detail(person_id)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed people views are not configured yet.",
        )
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found.")
    return templates.TemplateResponse(
        request,
        "pages/person_detail.html",
        {
            "title": person.full_name,
            "section": "people",
            "current_user": current_user,
            "person": person,
        },
    )


@web_router.post("/people/{person_id}/photo")
async def people_upload_photo(
    request: Request,
    person_id: int,
    file: UploadFile = File(...),
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    try:
        await _get_people_service_for_request(request).upload_photo(
            person_id=person_id,
            filename=file.filename or "photo",
            content=await file.read(),
            content_type=file.content_type,
        )
    except (PersonNotFoundError, UnsupportedUploadError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RedirectResponse(url=f"/people/{person_id}", status_code=status.HTTP_303_SEE_OTHER)


@web_router.post("/people/{person_id}/photo/delete")
async def people_delete_photo(
    request: Request,
    person_id: int,
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    try:
        await _get_people_service_for_request(request).delete_photo(person_id)
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return RedirectResponse(url=f"/people/{person_id}", status_code=status.HTTP_303_SEE_OTHER)


@web_router.post("/people/{person_id}/documents")
async def people_upload_document(
    request: Request,
    person_id: int,
    file: UploadFile = File(...),
    group_id: str | None = Form(default=None),
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    try:
        await _get_people_service_for_request(request).upload_document(
            person_id=person_id,
            filename=file.filename or "document",
            content=await file.read(),
            content_type=file.content_type,
            group_id=int(group_id) if group_id and group_id.strip() else None,
        )
    except (PersonNotFoundError, DuplicateDocumentError, UnsupportedUploadError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RedirectResponse(url=f"/people/{person_id}", status_code=status.HTTP_303_SEE_OTHER)


@web_router.post("/people/{person_id}/documents/{document_id}/delete")
async def people_delete_document(
    request: Request,
    person_id: int,
    document_id: int,
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    try:
        await _get_people_service_for_request(request).delete_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return RedirectResponse(url=f"/people/{person_id}", status_code=status.HTTP_303_SEE_OTHER)


@web_router.get("/groups")
async def groups_index(
    request: Request,
    q: str | None = None,
    current_user=Depends(require_authenticated_user),
):
    try:
        groups = await _get_groups_service_for_request(request).list_groups(query=q, limit=100)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed group views are not configured yet.",
        )
    return templates.TemplateResponse(
        request,
        "pages/groups.html",
        {
            "title": "Groups",
            "section": "groups",
            "current_user": current_user,
            "groups": groups,
            "query": q or "",
        },
    )


@web_router.get("/groups/{group_id}")
async def groups_detail(request: Request, group_id: int, current_user=Depends(require_authenticated_user)):
    try:
        group = await _get_groups_service_for_request(request).get_group_detail(group_id)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed group views are not configured yet.",
        )
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    return templates.TemplateResponse(
        request,
        "pages/group_detail.html",
        {
            "title": group.name,
            "section": "groups",
            "current_user": current_user,
            "group": group,
        },
    )


@web_router.get("/groups/{group_id}/semester-transfer")
async def groups_semester_transfer(
    request: Request,
    group_id: int,
    source_semester: int | None = None,
    target_semester: int | None = None,
    current_user=Depends(require_authenticated_user),
):
    current_user = _require_admin(current_user)
    preview = await _get_semester_transfer_service_for_request(request).preview_transfer(
        group_id=group_id,
        source_semester=source_semester,
        target_semester=target_semester,
    )
    return templates.TemplateResponse(
        request,
        "pages/semester_transfer.html",
        {
            "title": f"Semester transfer · {preview.group_name}",
            "section": "groups",
            "current_user": current_user,
            "preview": preview,
        },
    )


@web_router.post("/groups/{group_id}/semester-transfer")
async def groups_apply_semester_transfer(
    request: Request,
    group_id: int,
    target_semester: int = Form(...),
    person_ids: list[int] = Form(default=[]),
    role_ids: list[str] = Form(default=[]),
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    entries = [
        SemesterTransferEntry(
            person_id=person_id,
            role_id=(int(role_ids[index]) if index < len(role_ids) and role_ids[index].strip() else None),
        )
        for index, person_id in enumerate(person_ids)
    ]
    await _get_semester_transfer_service_for_request(request).apply_transfer(
        group_id=group_id,
        target_semester=target_semester,
        entries=entries,
    )
    return RedirectResponse(url=f"/groups/{group_id}", status_code=status.HTTP_303_SEE_OTHER)


@web_router.get("/courses")
async def courses_index(
    request: Request,
    q: str | None = None,
    current_user=Depends(require_authenticated_user),
):
    try:
        courses = await _get_courses_service_for_request(request).list_courses(query=q, limit=100)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed course views are not configured yet.",
        )
    return templates.TemplateResponse(
        request,
        "pages/courses.html",
        {
            "title": "Courses",
            "section": "courses",
            "current_user": current_user,
            "courses": courses,
            "query": q or "",
        },
    )


@web_router.get("/courses/{course_id}")
async def courses_detail(request: Request, course_id: int, current_user=Depends(require_authenticated_user)):
    try:
        course = await _get_courses_service_for_request(request).get_course_detail(course_id)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed course views are not configured yet.",
        )
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
    return templates.TemplateResponse(
        request,
        "pages/course_detail.html",
        {
            "title": course.name,
            "section": "courses",
            "current_user": current_user,
            "course": course,
        },
    )


@web_router.get("/search")
async def search_people_page(
    request: Request,
    birth_date_after: str | None = None,
    birth_date_before: str | None = None,
    pingvin_points_above: int | None = None,
    pingvin_points_below: int | None = None,
    include_groups: str | None = None,
    include_current_groups: str | None = None,
    exclude_groups: str | None = None,
    exclude_current_groups: str | None = None,
    include_courses: str | None = None,
    exclude_courses: str | None = None,
    current_user=Depends(require_authenticated_user),
):
    groups, courses = await asyncio.gather(
        _get_groups_service_for_request(request).list_groups(limit=200),
        _get_courses_service_for_request(request).list_courses(limit=200),
    )

    def parse_ids(raw: str | None) -> list[int]:
        if not raw:
            return []
        return [int(part.strip()) for part in raw.split(",") if part.strip().isdigit()]

    results = []
    if any(
        value not in (None, "", [])
        for value in [
            birth_date_after,
            birth_date_before,
            pingvin_points_above,
            pingvin_points_below,
            include_groups,
            include_current_groups,
            exclude_groups,
            exclude_current_groups,
            include_courses,
            exclude_courses,
        ]
    ):
        results = await _get_search_service_for_request(request).search_people(
            SearchQuery(
                birth_date_after=date.fromisoformat(birth_date_after) if birth_date_after else None,
                birth_date_before=date.fromisoformat(birth_date_before) if birth_date_before else None,
                pingvin_points_above=pingvin_points_above,
                pingvin_points_below=pingvin_points_below,
                include_groups=SearchFilterList(ids=parse_ids(include_groups)) if include_groups else None,
                include_current_groups=SearchFilterList(ids=parse_ids(include_current_groups)) if include_current_groups else None,
                exclude_groups=SearchFilterList(ids=parse_ids(exclude_groups)) if exclude_groups else None,
                exclude_current_groups=SearchFilterList(ids=parse_ids(exclude_current_groups)) if exclude_current_groups else None,
                include_courses=SearchFilterList(ids=parse_ids(include_courses)) if include_courses else None,
                exclude_courses=SearchFilterList(ids=parse_ids(exclude_courses)) if exclude_courses else None,
            )
        )

    return templates.TemplateResponse(
        request,
        "pages/search.html",
        {
            "title": "Search",
            "section": "search",
            "current_user": current_user,
            "groups": groups,
            "courses": courses,
            "results": results,
            "form": {
                "birth_date_after": birth_date_after or "",
                "birth_date_before": birth_date_before or "",
                "pingvin_points_above": pingvin_points_above or "",
                "pingvin_points_below": pingvin_points_below or "",
                "include_groups": include_groups or "",
                "include_current_groups": include_current_groups or "",
                "exclude_groups": exclude_groups or "",
                "exclude_current_groups": exclude_current_groups or "",
                "include_courses": include_courses or "",
                "exclude_courses": exclude_courses or "",
            },
        },
    )


@web_router.get("/users")
async def users_index(
    request: Request,
    q: str | None = None,
    current_user=Depends(require_authenticated_user),
):
    current_user = _require_admin(current_user)
    try:
        users = await _get_users_service_for_request(request).list_users(query=q, limit=100)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed user views are not configured yet.",
        )
    return templates.TemplateResponse(
        request,
        "pages/users.html",
        {
            "title": "Users",
            "section": "users",
            "current_user": current_user,
            "users": users,
            "query": q or "",
        },
    )


@web_router.get("/users/{user_account_id}")
async def users_detail(
    request: Request,
    user_account_id: int,
    current_user=Depends(require_authenticated_user),
):
    current_user = _require_admin(current_user)
    try:
        user = await _get_users_service_for_request(request).get_user_detail(user_account_id)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed user views are not configured yet.",
        )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return templates.TemplateResponse(
        request,
        "pages/user_detail.html",
        {
            "title": user.username,
            "section": "users",
            "current_user": current_user,
            "user_account": user,
        },
    )


@web_router.get("/registrations")
async def registrations_index(request: Request, current_user=Depends(require_authenticated_user)):
    current_user = _require_admin(current_user)
    registrations = await _get_registrations_service_for_request(request).list_pending()
    return templates.TemplateResponse(
        request,
        "pages/registrations.html",
        {
            "title": "Registrations",
            "section": "registrations",
            "current_user": current_user,
            "registrations": registrations,
        },
    )


@web_router.post("/registrations")
async def registrations_create_invite(
    request: Request,
    email: str = Form(...),
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    await _get_registrations_service_for_request(request).create_invitation(email)
    return RedirectResponse(url="/registrations", status_code=status.HTTP_303_SEE_OTHER)


@web_router.post("/registrations/{registration_id}/approve")
async def registrations_approve(
    request: Request,
    registration_id: int,
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    try:
        person_id = await _get_registrations_service_for_request(request).approve_registration(registration_id)
    except (RegistrationNotFoundError, RegistrationConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RedirectResponse(url=f"/people/{person_id}", status_code=status.HTTP_303_SEE_OTHER)


@web_router.post("/registrations/{registration_id}/reject")
async def registrations_reject(
    request: Request,
    registration_id: int,
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    try:
        await _get_registrations_service_for_request(request).reject_registration(registration_id)
    except RegistrationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return RedirectResponse(url="/registrations", status_code=status.HTTP_303_SEE_OTHER)


@web_router.get("/register/{token}")
async def registration_form(request: Request, token: str):
    detail = await _get_registrations_service_for_request(request).get_invitation_by_token(token)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registration not found.")
    return templates.TemplateResponse(
        request,
        "pages/register_form.html",
        {
            "title": "Volunteer registration",
            "section": "register",
            "current_user": getattr(request.state, "current_user", None),
            "registration": detail,
        },
    )


@web_router.post("/register/{token}")
async def registration_submit(
    request: Request,
    token: str,
    first_name: str | None = Form(default=None),
    last_name: str = Form(...),
    phone: str | None = Form(default=None),
    birth_date: str | None = Form(default=None),
    gender: str = Form(default="A"),
    address: str | None = Form(default=None),
    postal_code: str | None = Form(default=None),
    employment_status: str | None = Form(default=None),
):
    try:
        detail = await _get_registrations_service_for_request(request).submit_registration(
            token,
            RegistrationSubmissionInput(
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                birth_date=date.fromisoformat(birth_date) if birth_date else None,
                gender=gender,
                address=address,
                postal_code=postal_code,
                employment_status=int(employment_status) if employment_status and employment_status.strip() else None,
            ),
        )
    except RegistrationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RegistrationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "pages/register_form.html",
        {
            "title": "Volunteer registration",
            "section": "register",
            "current_user": getattr(request.state, "current_user", None),
            "registration": detail,
            "submitted": True,
        },
    )
