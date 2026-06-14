"""Errors for position management (role assignments and course completions)."""

from __future__ import annotations


class RoleAssignmentsError(RuntimeError):
    pass


class VolunteerNotFoundError(RoleAssignmentsError):
    pass


class InvalidCourseCompletionError(RoleAssignmentsError):
    pass


class DuplicateCourseCompletionError(RoleAssignmentsError):
    pass


class CourseCompletionNotFoundError(RoleAssignmentsError):
    pass


class InvalidRoleAssignmentError(RoleAssignmentsError):
    pass


class DuplicateRoleAssignmentError(RoleAssignmentsError):
    pass


class RoleAssignmentNotFoundError(RoleAssignmentsError):
    pass
