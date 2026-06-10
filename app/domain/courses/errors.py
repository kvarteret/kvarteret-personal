from __future__ import annotations


class CourseDeleteBlockedError(ValueError):
    def __init__(self, blockers: list[str]) -> None:
        super().__init__("Course deletion is blocked.")
        self.blockers = blockers


class InvalidCourseCompletionError(ValueError):
    pass


class DuplicateCourseCompletionError(ValueError):
    pass


class CourseCompletionNotFoundError(ValueError):
    pass
