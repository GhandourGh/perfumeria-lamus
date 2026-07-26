from werkzeug.security import check_password_hash

import database as db


def test_password_hash_does_not_require_scrypt():
    password_hash = db.hash_secret("admin123")

    assert password_hash.startswith("pbkdf2:sha256:600000$")
    assert check_password_hash(password_hash, "admin123")
