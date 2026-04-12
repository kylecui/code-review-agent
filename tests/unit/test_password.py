from agent_review.auth.password import hash_password, password_needs_rehash, verify_password


def test_hash_password() -> None:
    password = "correct-horse-battery-staple"
    hashed = hash_password(password)

    assert isinstance(hashed, str)
    assert hashed
    assert hashed != password


def test_verify_password_correct() -> None:
    password = "correct-horse-battery-staple"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_wrong() -> None:
    password = "correct-horse-battery-staple"
    hashed = hash_password(password)

    assert verify_password("wrong-password", hashed) is False


def test_password_needs_rehash() -> None:
    hashed = hash_password("correct-horse-battery-staple")

    assert password_needs_rehash(hashed) is False
