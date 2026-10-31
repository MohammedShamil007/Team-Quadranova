
import hashlib
import hmac
import re
import secrets


SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LENGTH = 32


def validate_password(password: str) -> None:
    if len(password) <= 8:
        raise ValueError("Password must contain more than 8 characters.")

    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain an uppercase letter.")

    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain a lowercase letter.")

    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must contain a special character.")


def hash_password(password: str) -> tuple[str, str]:
    validate_password(password)

    salt = secrets.token_bytes(16)

    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=KEY_LENGTH,
    )

    return derived_key.hex(), salt.hex()


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    try:
        derived_key = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt),
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=KEY_LENGTH,
        )

        return hmac.compare_digest(derived_key.hex(), password_hash)

    except (ValueError, TypeError):
        return False


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
