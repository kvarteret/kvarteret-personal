from app.auth.legacy_passwords import (
    build_aspnet_identity_v3_hash,
    parse_aspnet_identity_hash,
    verify_aspnet_identity_hash,
)


SYNTHETIC_ADMIN_HASH = build_aspnet_identity_v3_hash(
    "SyntheticAdminPassword123!",
    salt=bytes.fromhex("11223344556677889900aabbccddeeff"),
    iterations=100_000,
    prf=2,
)


def test_can_verify_generated_aspnet_identity_v3_hash() -> None:
    encoded = build_aspnet_identity_v3_hash(
        "correct horse battery staple",
        salt=bytes.fromhex("00112233445566778899aabbccddeeff"),
        iterations=100_000,
        prf=2,
    )

    assert verify_aspnet_identity_hash(encoded, "correct horse battery staple") is True
    assert verify_aspnet_identity_hash(encoded, "wrong password") is False


def test_can_parse_synthetic_admin_hash_format() -> None:
    parsed = parse_aspnet_identity_hash(SYNTHETIC_ADMIN_HASH)

    assert parsed.format_marker == 1
    assert parsed.hash_name == "sha512"
    assert parsed.iterations == 100_000
    assert len(parsed.salt) == 16
    assert len(parsed.subkey) == 32


def test_synthetic_admin_hash_rejects_wrong_password() -> None:
    assert verify_aspnet_identity_hash(SYNTHETIC_ADMIN_HASH, "definitely-not-the-right-password") is False
