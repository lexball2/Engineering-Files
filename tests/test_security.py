from backend.core.security import create_token, decode_token


def test_jwt_requires_expected_claims():
    token = create_token({"sub": "YOU1", "role": "admin", "ver": 3})
    payload = decode_token(token)

    assert payload is not None
    assert payload["sub"] == "YOU1"
    assert payload["ver"] == 3
    assert decode_token(token + "tampered") is None


def test_jwt_without_token_version_is_rejected():
    token = create_token({"sub": "YOU1", "role": "admin"})
    assert decode_token(token) is None
