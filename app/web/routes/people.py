from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse

from app.dependencies import get_people_service, require_authenticated_user, require_web_admin_user
from app.errors import NotConfiguredError
from app.observability import log_admin_activity
from app.services.people import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    PeopleService,
    PersonNotFoundError,
    UnsupportedUploadError,
)
from app.web.templates import templates

router = APIRouter()
PEOPLE_PAGE_SIZE = 20


@router.get("/people")
async def people_index(
    request: Request,
    q: str | None = None,
    offset: int = 0,
    current_user=Depends(require_authenticated_user),
    people_service: PeopleService = Depends(get_people_service),
):
    try:
        page = await people_service.list_people_page(query=q, limit=PEOPLE_PAGE_SIZE, offset=offset)
    except NotConfiguredError:
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
        return templates.TemplateResponse(request, "components/people_results.html", context)
    return templates.TemplateResponse(request, "pages/people.html", context)


@router.get("/people/{person_id}")
async def people_detail(
    request: Request,
    person_id: int,
    current_user=Depends(require_authenticated_user),
    people_service: PeopleService = Depends(get_people_service),
):
    try:
        person = await people_service.get_person_detail(person_id)
    except NotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed people views are not configured yet.",
        )
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found.")
    if current_user.role.value == "admin":
        log_admin_activity(
            request=request,
            user=current_user,
            action="person.view_detail",
            subject_type="person",
            subject_id=person_id,
        )
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


@router.post("/people/{person_id}/photo")
async def people_upload_photo(
    request: Request,
    person_id: int,
    file: UploadFile = File(...),
    current_user=Depends(require_web_admin_user),
    people_service: PeopleService = Depends(get_people_service),
):
    try:
        await people_service.upload_photo(
            person_id=person_id,
            filename=file.filename or "photo",
            content=await file.read(),
            content_type=file.content_type,
        )
    except (PersonNotFoundError, UnsupportedUploadError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="person.upload_photo",
        subject_type="person",
        subject_id=person_id,
        details={"filename": file.filename},
    )
    return RedirectResponse(url=f"/people/{person_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/people/{person_id}/photo/delete")
async def people_delete_photo(
    request: Request,
    person_id: int,
    current_user=Depends(require_web_admin_user),
    people_service: PeopleService = Depends(get_people_service),
):
    try:
        await people_service.delete_photo(person_id)
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="person.delete_photo",
        subject_type="person",
        subject_id=person_id,
    )
    return RedirectResponse(url=f"/people/{person_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/people/{person_id}/documents")
async def people_upload_document(
    request: Request,
    person_id: int,
    file: UploadFile = File(...),
    group_id: str | None = Form(default=None),
    current_user=Depends(require_web_admin_user),
    people_service: PeopleService = Depends(get_people_service),
):
    try:
        normalized_group_id = int(group_id) if group_id and group_id.strip() else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group id must be a number.") from exc

    try:
        await people_service.upload_document(
            person_id=person_id,
            filename=file.filename or "document",
            content=await file.read(),
            content_type=file.content_type,
            group_id=normalized_group_id,
        )
    except (PersonNotFoundError, DuplicateDocumentError, UnsupportedUploadError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="person.upload_document",
        subject_type="person",
        subject_id=person_id,
        details={"filename": file.filename, "group_id": normalized_group_id},
    )
    return RedirectResponse(url=f"/people/{person_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/people/{person_id}/documents/{document_id}/delete")
async def people_delete_document(
    request: Request,
    person_id: int,
    document_id: int,
    current_user=Depends(require_web_admin_user),
    people_service: PeopleService = Depends(get_people_service),
):
    try:
        await people_service.delete_document_for_person(person_id, document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="person.delete_document",
        subject_type="document",
        subject_id=document_id,
        details={"person_id": person_id},
    )
    return RedirectResponse(url=f"/people/{person_id}", status_code=status.HTTP_303_SEE_OTHER)
