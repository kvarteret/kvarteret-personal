from __future__ import annotations

import argparse
import asyncio

from app.auth.roles import UserRole
from app.runtime import build_application_container


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

    container = build_application_container()
    try:
        auth_user_id = await container.supabase_auth_gateway.create_user(
            email=args.email,
            password=args.password,
            metadata={"bootstrap": True, "username": args.username},
        )
        account = await container.auth_repository.create_direct_user_account(
            auth_user_id=auth_user_id,
            username=args.username,
            email=args.email,
            display_name=args.display_name,
            role=role_map[args.role],
        )
        print(f"Created auth user {auth_user_id} with user_accounts.id={account.id}")
    finally:
        await container.aclose()


if __name__ == "__main__":
    asyncio.run(main())
