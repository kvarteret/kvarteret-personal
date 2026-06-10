"""Role assignment domain — owns ``assignment_roles`` and ``role_assignments`` tables."""

from app.domain.role_assignments.tables import assignment_roles, role_assignments

__all__ = ["assignment_roles", "role_assignments"]
