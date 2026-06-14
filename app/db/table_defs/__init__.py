"""Auth and storage schema reflections (external Supabase schemas).

Public-schema tables live in their owning domain modules; import them
from there or via the ``app.db.tables`` aggregator. This package keeps
only the non-public schema reflections.
"""

from app.db.table_defs.auth import (
    auth_identities,
    auth_metadata,
    auth_refresh_tokens,
    auth_sessions,
    auth_users,
)
from app.db.table_defs.storage import storage_metadata, storage_objects

__all__ = [
    "auth_identities",
    "auth_metadata",
    "auth_refresh_tokens",
    "auth_sessions",
    "auth_users",
    "storage_metadata",
    "storage_objects",
]
