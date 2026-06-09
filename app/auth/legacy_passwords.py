from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from struct import pack, unpack


_PRF_TO_HASH = {
    0: "sha1",
    1: "sha256",
    2: "sha512",
}


@dataclass(frozen=True)
class ParsedLegacyHash:
    format_marker: int
    hash_name: str
    iterations: int
    salt: bytes
    subkey: bytes


def parse_aspnet_identity_hash(encoded_hash: str) -> ParsedLegacyHash:
    raw = base64.b64decode(encoded_hash)
    if not raw:
        raise ValueError("Password hash is empty.")

    format_marker = raw[0]

    if format_marker == 0:
        if len(raw) != 49:
            raise ValueError("Unsupported ASP.NET Identity v2 hash length.")
        salt = raw[1:17]
        subkey = raw[17:]
        return ParsedLegacyHash(
            format_marker=format_marker,
            hash_name="sha1",
            iterations=1000,
            salt=salt,
            subkey=subkey,
        )

    if format_marker == 1:
        if len(raw) < 13:
            raise ValueError("Unsupported ASP.NET Identity v3 hash length.")
        prf, iterations, salt_length = unpack(">III", raw[1:13])
        hash_name = _PRF_TO_HASH.get(prf)
        if hash_name is None:
            raise ValueError(f"Unsupported PRF identifier: {prf}.")
        salt_start = 13
        salt_end = salt_start + salt_length
        salt = raw[salt_start:salt_end]
        subkey = raw[salt_end:]
        if not salt or not subkey:
            raise ValueError("ASP.NET Identity v3 hash is missing salt or subkey.")
        return ParsedLegacyHash(
            format_marker=format_marker,
            hash_name=hash_name,
            iterations=iterations,
            salt=salt,
            subkey=subkey,
        )

    raise ValueError(f"Unsupported ASP.NET Identity format marker: {format_marker}.")


def verify_aspnet_identity_hash(encoded_hash: str, password: str) -> bool:
    parsed = parse_aspnet_identity_hash(encoded_hash)
    derived = hashlib.pbkdf2_hmac(
        parsed.hash_name,
        password.encode("utf-8"),
        parsed.salt,
        parsed.iterations,
        dklen=len(parsed.subkey),
    )
    return hmac.compare_digest(derived, parsed.subkey)


def build_aspnet_identity_v3_hash(
    password: str,
    *,
    salt: bytes,
    iterations: int = 100_000,
    prf: int = 2,
    dklen: int = 32,
) -> str:
    hash_name = _PRF_TO_HASH[prf]
    subkey = hashlib.pbkdf2_hmac(
        hash_name, password.encode("utf-8"), salt, iterations, dklen
    )
    payload = b"".join(
        [
            bytes([1]),
            pack(">I", prf),
            pack(">I", iterations),
            pack(">I", len(salt)),
            salt,
            subkey,
        ]
    )
    return base64.b64encode(payload).decode("ascii")
