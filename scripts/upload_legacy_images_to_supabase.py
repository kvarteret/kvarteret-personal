from __future__ import annotations

import argparse
import asyncio
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import func, select

from app.config import get_settings
from app.db.session import DatabaseRuntimeManager
from app.db.tables import personal_bilde, storage_objects
from app.services.storage import StorageService


DEFAULT_SOURCE_DIR = Path("data/legacy-images/images")
DEFAULT_FAILURE_LOG = Path("data/legacy-images-upload-failures.txt")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload the recovered Azure images archive into the Supabase personnel-photos bucket."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"Directory containing recovered image files. Default: {DEFAULT_SOURCE_DIR}",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of concurrent upload workers. Default: 8",
    )
    parser.add_argument(
        "--db-backed-only",
        action="store_true",
        help="Upload only filenames referenced by public.personal_bilde.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap for a partial test run.",
    )
    parser.add_argument(
        "--failure-log",
        type=Path,
        default=DEFAULT_FAILURE_LOG,
        help=f"Path to append failures. Default: {DEFAULT_FAILURE_LOG}",
    )
    return parser


async def fetch_existing_storage_names(bucket_id: str) -> set[str]:
    async_session_maker = DatabaseRuntimeManager(get_settings()).get_session_factory()
    async with async_session_maker() as session:
        result = await session.execute(
            select(storage_objects.c.name).where(storage_objects.c.bucket_id == bucket_id)
        )
    return {name for name in result.scalars().all() if name}


async def fetch_expected_photo_names() -> set[str]:
    async_session_maker = DatabaseRuntimeManager(get_settings()).get_session_factory()
    async with async_session_maker() as session:
        result = await session.execute(
            select(func.concat(personal_bilde.c.sha1, ".", personal_bilde.c.filetype))
        )
    return {name for name in result.scalars().all() if name}


def collect_local_files(source_dir: Path) -> dict[str, Path]:
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
    files = {}
    for path in sorted(source_dir.iterdir()):
        if path.is_file():
            files[path.name] = path
    if not files:
        raise FileNotFoundError(f"No files found in {source_dir}")
    return files


def _upload_one(source_path: Path, object_name: str) -> str:
    settings = get_settings()
    service = StorageService(settings)
    content = source_path.read_bytes()
    content_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
    service.upload_photo(object_name, content, content_type)
    return object_name


def _upload_one_safe(source_path: Path, object_name: str) -> tuple[str, str | None]:
    try:
        _upload_one(source_path, object_name)
        return object_name, None
    except Exception as exc:  # pragma: no cover - operational path
        return object_name, str(exc)


async def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    local_files = collect_local_files(args.source_dir)
    expected_names = await fetch_expected_photo_names()
    existing_names = await fetch_existing_storage_names(settings.photo_bucket)

    local_names = set(local_files)
    orphaned_local_names = sorted(local_names - expected_names)
    missing_local_expected_names = sorted(expected_names - local_names)

    if args.db_backed_only:
        candidate_names = sorted(local_names & expected_names)
    else:
        candidate_names = sorted(local_names)

    missing_storage_names = [name for name in candidate_names if name not in existing_names]
    if args.limit is not None:
        missing_storage_names = missing_storage_names[: args.limit]

    selected_files = {name: local_files[name] for name in missing_storage_names}

    print(f"source_dir={args.source_dir}")
    print(f"local_files={len(local_names)}")
    print(f"db_backed_files={len(expected_names)}")
    print(f"already_in_bucket={len(existing_names)}")
    print(f"orphaned_local_files={len(orphaned_local_names)}")
    print(f"missing_local_expected_files={len(missing_local_expected_names)}")
    print(f"selected_for_upload={len(selected_files)}")

    if missing_local_expected_names:
        preview = ", ".join(missing_local_expected_names[:10])
        print(f"missing_local_expected_preview={preview}")

    if orphaned_local_names:
        preview = ", ".join(orphaned_local_names[:10])
        print(f"orphaned_local_preview={preview}")

    if not selected_files:
        if args.failure_log.exists():
            args.failure_log.unlink()
        print("Nothing to upload.")
        return

    loop = asyncio.get_running_loop()
    failures: list[tuple[str, str]] = []
    uploaded = 0
    args.failure_log.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = []
        for object_name, source_path in selected_files.items():
            futures.append(loop.run_in_executor(executor, _upload_one_safe, source_path, object_name))
        for future in asyncio.as_completed(futures):
            object_name, error = await future
            if error is None:
                uploaded += 1
                if uploaded % 250 == 0 or uploaded == len(selected_files):
                    print(f"uploaded {uploaded}/{len(selected_files)}")
            else:  # pragma: no cover - operational path
                failures.append((object_name, error))

    if failures:
        with args.failure_log.open("w", encoding="utf-8") as handle:
            for name, error in failures:
                handle.write(f"{name}\t{error}\n")
    elif args.failure_log.exists():
        args.failure_log.unlink()

    print(f"uploaded_total={uploaded}")
    print(f"failures={len(failures)}")
    if failures:
        preview = ", ".join(name for name, _ in failures[:10])
        print(f"failure_preview={preview}")


if __name__ == "__main__":
    asyncio.run(main())
