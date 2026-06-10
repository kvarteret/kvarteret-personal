from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class CourseListItem:
    course_id: int
    name: str
    description: str | None
    created_at: datetime | None


@dataclass(slots=True)
class RequiredGroupItem:
    group_id: int
    group_name: str


@dataclass(slots=True)
class CourseCompletionItem:
    completion_id: int
    volunteer_id: int
    volunteer_name: str
    completed_semester_code: int
    completed_semester_label: str


@dataclass(slots=True)
class CourseDetail:
    course_id: int
    name: str
    description: str | None
    created_at: datetime | None
    required_groups: list[RequiredGroupItem]
    recent_completions: list[CourseCompletionItem]
    delete_blockers: list[str]
