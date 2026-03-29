from __future__ import annotations

from pathlib import Path
from shutil import copy2


def main() -> None:
    source_root = Path("app/static")
    destination_root = Path("public/static")

    if destination_root.exists():
        for path in sorted(destination_root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()

    destination_root.mkdir(parents=True, exist_ok=True)

    for source_path in source_root.rglob("*"):
        if not source_path.is_file():
            continue
        relative_path = source_path.relative_to(source_root)
        destination_path = destination_root / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        copy2(source_path, destination_path)

    print(f"Prepared {destination_root}")


if __name__ == "__main__":
    main()
