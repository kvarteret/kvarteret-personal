from __future__ import annotations

import argparse

from app.config import get_settings
from app.services.storage import StorageService


CONFIRMATION_TOKEN = "DELETE-ALL-STORAGE-DATA"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Empty every Supabase Storage bucket configured for the current project."
    )
    parser.add_argument(
        "--confirm",
        required=True,
        help=f"Required safety token. Must be exactly {CONFIRMATION_TOKEN}.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.confirm != CONFIRMATION_TOKEN:
        raise SystemExit(f"Refusing to run without --confirm {CONFIRMATION_TOKEN}")

    settings = get_settings()
    service = StorageService(settings)
    try:
        buckets = service.list_buckets()
        if not buckets:
            print("No buckets found.")
            return

        print(f"Found {len(buckets)} bucket(s).")
        for bucket in buckets:
            bucket_id = bucket.get("id")
            if not isinstance(bucket_id, str) or not bucket_id:
                continue
            message = service.empty_bucket(bucket_id)
            print(f"{bucket_id}: {message}")
    finally:
        service.close()


if __name__ == "__main__":
    main()
