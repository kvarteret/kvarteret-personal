from __future__ import annotations

import ast
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = ROOT / "app" / "locales"


def compile_catalog(source_path: Path, destination_path: Path) -> None:
    messages = _parse_po_file(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(_build_mo_file(messages))


def _parse_po_file(source_path: Path) -> dict[str, str]:
    messages: dict[str, str] = {}
    msgid: str | None = None
    msgstr: str | None = None
    state: str | None = None

    def finalize() -> None:
        nonlocal msgid, msgstr, state
        if msgid is not None and msgstr is not None:
            messages[msgid] = msgstr
        msgid = None
        msgstr = None
        state = None

    for raw_line in source_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            finalize()
            continue
        if line.startswith("#"):
            continue
        if line.startswith("msgid "):
            finalize()
            msgid = _parse_po_string(line[6:])
            state = "msgid"
            continue
        if line.startswith("msgstr "):
            msgstr = _parse_po_string(line[7:])
            state = "msgstr"
            continue
        if line.startswith('"'):
            if state == "msgid" and msgid is not None:
                msgid += _parse_po_string(line)
            elif state == "msgstr" and msgstr is not None:
                msgstr += _parse_po_string(line)

    finalize()
    return messages


def _parse_po_string(token: str) -> str:
    return ast.literal_eval(token)


def _build_mo_file(messages: dict[str, str]) -> bytes:
    sorted_items = sorted(messages.items(), key=lambda item: item[0])
    ids = [item[0].encode("utf-8") for item in sorted_items]
    strings = [item[1].encode("utf-8") for item in sorted_items]

    ids_blob = b"".join(message + b"\x00" for message in ids)
    strings_blob = b"".join(message + b"\x00" for message in strings)

    message_count = len(sorted_items)
    original_table_offset = 7 * 4
    translated_table_offset = original_table_offset + message_count * 8
    original_strings_offset = translated_table_offset + message_count * 8
    translated_strings_offset = original_strings_offset + len(ids_blob)

    output = bytearray()
    output.extend(
        struct.pack(
            "Iiiiiii",
            0x950412DE,
            0,
            message_count,
            original_table_offset,
            translated_table_offset,
            0,
            0,
        )
    )

    current_offset = original_strings_offset
    for message in ids:
        output.extend(struct.pack("II", len(message), current_offset))
        current_offset += len(message) + 1

    current_offset = translated_strings_offset
    for message in strings:
        output.extend(struct.pack("II", len(message), current_offset))
        current_offset += len(message) + 1

    output.extend(ids_blob)
    output.extend(strings_blob)
    return bytes(output)


def main() -> None:
    for source_path in LOCALES_DIR.glob("*/LC_MESSAGES/*.po"):
        compile_catalog(source_path, source_path.with_suffix(".mo"))


if __name__ == "__main__":
    main()
