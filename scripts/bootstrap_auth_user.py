from __future__ import annotations

import argparse
import asyncio

from app.auth.repository import get_auth_repository
from app.auth.roles import UserRole
from app.auth.supabase_auth import get_supabase_auth_gateway


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create a direct auth-backed user account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", default=None)
    parser.add_argument(
        "--role",
        default="admin",
        choices=["admin", "group_admin", "volunteer", "viewer"],
    )
    args = parser.parse_args()

    role_map = {
        "admin": UserRole.ADMIN,
        "group_admin": UserRole.GROUP_ADMIN,
        "volunteer": UserRole.VOLUNTEER,
        "viewer": UserRole.VIEWER,
    }

    gateway = get_supabase_auth_gateway()
    repository = get_auth_repository()
    auth_user_id = await gateway.create_user(
        email=args.email,
        password=args.password,
        metadata={"bootstrap": True, "username": args.username},
    )
    account = await repository.create_direct_user_account(
        auth_user_id=auth_user_id,
        username=args.username,
        email=args.email,
        display_name=args.display_name,
        role=role_map[args.role],
    )
    print(f"Created auth user {auth_user_id} with user_accounts.id={account.id}")


if __name__ == "__main__":
    asyncio.run(main())
