from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = ROOT / "openapi.json"


def build_openapi_schema() -> dict[str, Any]:
    return create_app().openapi()


def render_openapi_schema(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI schema.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to write the OpenAPI JSON artifact.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the existing artifact differs from the generated schema.",
    )
    args = parser.parse_args()

    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    rendered = render_openapi_schema(build_openapi_schema())

    if args.check:
        if not output_path.exists():
            print(f"{output_path} does not exist.")
            return 1
        existing = output_path.read_text()
        if existing != rendered:
            print(f"{output_path} is stale. Run: python scripts/export_openapi.py")
            return 1
        return 0

    output_path.write_text(rendered)
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
