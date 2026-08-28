import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
DATABASE_FILE = BACKEND_DIR / "data" / "access_keys.sqlite3"
KEY_PATTERN = re.compile(r"^[0-9]{9}$")
DEVICE_PATTERN = re.compile(r"^[a-f0-9-]{32,64}$", re.IGNORECASE)
PBKDF2_ITERATIONS = 600_000
SESSION_LIFETIME_SECONDS = 30 * 24 * 60 * 60
MAX_FAILED_ATTEMPTS = 5
LOCK_SECONDS = 10 * 60


@dataclass
class KeyStoreError(Exception):
    status_code: int
    message: str


def load_local_env() -> None:
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_pepper() -> str:
    pepper = os.getenv("ACCESS_KEY_PEPPER", "").strip()
    if len(pepper) < 32 or pepper.startswith("replace_"):
        raise KeyStoreError(
            503,
            "ACCESS_KEY_PEPPER is not configured. Add a long random value to backend/.env.",
        )
    return pepper


def verify_admin_access_key(admin_key: str) -> None:
    expected = os.getenv("ADMIN_ACCESS_KEY", "777333111").strip()
    if not KEY_PATTERN.fullmatch(expected):
        raise KeyStoreError(
            503,
            "ADMIN_ACCESS_KEY is not configured as a 9-digit value in backend/.env.",
        )
    if not hmac.compare_digest(admin_key.strip(), expected):
        raise KeyStoreError(401, "Admin access key is not valid.")


def is_admin_access_key(access_key: str) -> bool:
    expected = os.getenv("ADMIN_ACCESS_KEY", "777333111").strip()
    if not KEY_PATTERN.fullmatch(expected):
        raise KeyStoreError(
            503,
            "ADMIN_ACCESS_KEY is not configured as a 9-digit value in backend/.env.",
        )
    return hmac.compare_digest(access_key.strip(), expected)


def connect() -> sqlite3.Connection:
    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS access_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL UNIQUE,
                lookup_hash TEXT NOT NULL UNIQUE,
                salt TEXT NOT NULL,
                key_hash TEXT NOT NULL,
                device_id TEXT,
                activated_at INTEGER,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                key_id INTEGER NOT NULL,
                device_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (key_id) REFERENCES access_keys(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS admin_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                device_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rate_limits (
                subject TEXT PRIMARY KEY,
                failure_count INTEGER NOT NULL,
                first_failure_at INTEGER NOT NULL,
                locked_until INTEGER
            );

            CREATE TABLE IF NOT EXISTS demo_announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            """
        )


def lookup_hash(access_key: str) -> str:
    return hmac.new(
        get_pepper().encode("utf-8"),
        access_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def password_hash(access_key: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        access_key.encode("utf-8"),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    ).hex()


def require_valid_inputs(access_key: str, device_id: str) -> None:
    if not KEY_PATTERN.fullmatch(access_key):
        raise KeyStoreError(400, "Enter a valid 9-digit access key.")
    if not DEVICE_PATTERN.fullmatch(device_id):
        raise KeyStoreError(400, "This device registration is invalid. Refresh and try again.")


def check_rate_limit(connection: sqlite3.Connection, subject: str, now: int) -> None:
    row = connection.execute(
        "SELECT failure_count, first_failure_at, locked_until FROM rate_limits WHERE subject = ?",
        (subject,),
    ).fetchone()
    if not row:
        return
    if row["locked_until"] and row["locked_until"] > now:
        remaining = max(1, (row["locked_until"] - now + 59) // 60)
        raise KeyStoreError(429, f"Too many attempts. Try again in {remaining} minute(s).")
    if now - row["first_failure_at"] > LOCK_SECONDS:
        connection.execute("DELETE FROM rate_limits WHERE subject = ?", (subject,))


def record_failed_attempt(connection: sqlite3.Connection, subject: str, now: int) -> None:
    row = connection.execute(
        "SELECT failure_count, first_failure_at FROM rate_limits WHERE subject = ?",
        (subject,),
    ).fetchone()
    if not row or now - row["first_failure_at"] > LOCK_SECONDS:
        connection.execute(
            "INSERT OR REPLACE INTO rate_limits(subject, failure_count, first_failure_at, locked_until) VALUES (?, ?, ?, NULL)",
            (subject, 1, now),
        )
        return

    failures = row["failure_count"] + 1
    locked_until = now + LOCK_SECONDS if failures >= MAX_FAILED_ATTEMPTS else None
    connection.execute(
        "UPDATE rate_limits SET failure_count = ?, locked_until = ? WHERE subject = ?",
        (failures, locked_until, subject),
    )


def create_session(connection: sqlite3.Connection, key_id: int, device_id: str, now: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    connection.execute(
        "DELETE FROM sessions WHERE expires_at <= ? OR (key_id = ? AND device_id = ?)",
        (now, key_id, device_id),
    )
    connection.execute(
        "INSERT INTO sessions(token_hash, key_id, device_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (token_hash, key_id, device_id, now + SESSION_LIFETIME_SECONDS, now),
    )
    return token


def create_admin_session(connection: sqlite3.Connection, device_id: str, now: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    connection.execute(
        "DELETE FROM admin_sessions WHERE expires_at <= ? OR device_id = ?",
        (now, device_id),
    )
    connection.execute(
        "INSERT INTO admin_sessions(token_hash, device_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (token_hash, device_id, now + SESSION_LIFETIME_SECONDS, now),
    )
    return token


def activate_admin_session(access_key: str, device_id: str, subject: str) -> dict[str, str | int | bool]:
    require_valid_inputs(access_key, device_id)
    now = int(time.time())

    with connect() as connection:
        check_rate_limit(connection, subject, now)
        if not is_admin_access_key(access_key):
            record_failed_attempt(connection, subject, now)
            raise KeyStoreError(401, "The access key is not valid.")
        connection.execute("DELETE FROM rate_limits WHERE subject = ?", (subject,))
        token = create_admin_session(connection, device_id, now)
        return {
            "session_token": token,
            "expires_at": now + SESSION_LIFETIME_SECONDS,
            "is_admin": True,
            "message": "Admin console session verified for this device.",
        }


def activate_access_key(access_key: str, device_id: str, subject: str) -> dict[str, str | int]:
    require_valid_inputs(access_key, device_id)
    now = int(time.time())

    with connect() as connection:
        check_rate_limit(connection, subject, now)
        row = connection.execute(
            "SELECT id, salt, key_hash, device_id FROM access_keys WHERE lookup_hash = ?",
            (lookup_hash(access_key),),
        ).fetchone()

        if not row or not hmac.compare_digest(password_hash(access_key, row["salt"]), row["key_hash"]):
            record_failed_attempt(connection, subject, now)
            raise KeyStoreError(401, "The access key is not valid.")

        if row["device_id"] and row["device_id"] != device_id:
            raise KeyStoreError(409, "This access key is already active on another registered device.")

        if not row["device_id"]:
            connection.execute(
                "UPDATE access_keys SET device_id = ?, activated_at = ? WHERE id = ?",
                (device_id, now, row["id"]),
            )

        connection.execute("DELETE FROM rate_limits WHERE subject = ?", (subject,))
        token = create_session(connection, row["id"], device_id, now)
        return {
            "session_token": token,
            "expires_at": now + SESSION_LIFETIME_SECONDS,
            "is_admin": False,
            "message": "This device is registered for this access key.",
        }


def validate_session(token: str, device_id: str) -> bool:
    if not token or not DEVICE_PATTERN.fullmatch(device_id):
        return False
    now = int(time.time())
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT sessions.id
            FROM sessions
            JOIN access_keys ON access_keys.id = sessions.key_id
            WHERE sessions.token_hash = ?
              AND sessions.device_id = ?
              AND access_keys.device_id = ?
              AND sessions.expires_at > ?
            """,
            (token_hash, device_id, device_id, now),
        ).fetchone()
        admin_row = connection.execute(
            """
            SELECT id FROM admin_sessions
            WHERE token_hash = ? AND device_id = ? AND expires_at > ?
            """,
            (token_hash, device_id, now),
        ).fetchone()
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        connection.execute("DELETE FROM admin_sessions WHERE expires_at <= ?", (now,))
    return bool(row or admin_row)


def save_demo_announcement(message: str) -> None:
    cleaned = message.strip()[:240]
    if not cleaned:
        return
    with connect() as connection:
        connection.execute("INSERT INTO demo_announcements(message, created_at) VALUES (?, ?)", (cleaned, int(time.time())))
        connection.execute(
            "DELETE FROM demo_announcements WHERE id NOT IN (SELECT id FROM demo_announcements ORDER BY id DESC LIMIT 20)"
        )


def latest_demo_announcement() -> str | None:
    with connect() as connection:
        row = connection.execute("SELECT message FROM demo_announcements ORDER BY id DESC LIMIT 1").fetchone()
    return row["message"] if row else None


def validate_admin_session(token: str, device_id: str) -> bool:
    if not token or not DEVICE_PATTERN.fullmatch(device_id):
        return False
    now = int(time.time())
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with connect() as connection:
        row = connection.execute(
            "SELECT id FROM admin_sessions WHERE token_hash = ? AND device_id = ? AND expires_at > ?",
            (token_hash, device_id, now),
        ).fetchone()
        connection.execute("DELETE FROM admin_sessions WHERE expires_at <= ?", (now,))
    return bool(row)


def generate_access_keys(count: int) -> list[tuple[str, str]]:
    if count < 1 or count > 100:
        raise KeyStoreError(400, "Generate between 1 and 100 keys at a time.")

    created: list[tuple[str, str]] = []
    now = int(time.time())
    with connect() as connection:
        while len(created) < count:
            access_key = str(secrets.randbelow(900_000_000) + 100_000_000)
            salt = secrets.token_bytes(16).hex()
            label = f"RBK-{len(created) + 1:03d}-{secrets.token_hex(3).upper()}"
            try:
                connection.execute(
                    """
                    INSERT INTO access_keys(label, lookup_hash, salt, key_hash, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (label, lookup_hash(access_key), salt, password_hash(access_key, salt), now),
                )
            except sqlite3.IntegrityError:
                continue
            created.append((label, access_key))
    return created


def import_access_keys(access_keys: list[str], expected_count: int | None = None) -> int:
    normalized = [access_key.strip() for access_key in access_keys if access_key.strip()]
    if expected_count is not None and len(normalized) != expected_count:
        raise KeyStoreError(400, f"Expected {expected_count} keys, received {len(normalized)}.")
    if not normalized:
        raise KeyStoreError(400, "No access keys were provided.")
    if len(set(normalized)) != len(normalized):
        raise KeyStoreError(400, "Duplicate access keys were provided.")
    if any(not KEY_PATTERN.fullmatch(access_key) for access_key in normalized):
        raise KeyStoreError(400, "Every access key must be exactly 9 digits.")

    now = int(time.time())
    with connect() as connection:
        existing = connection.execute("SELECT COUNT(*) AS value FROM access_keys").fetchone()["value"]
        if existing:
            raise KeyStoreError(409, "The key database already contains keys. Import is blocked to avoid duplicates.")

        records = []
        for index, access_key in enumerate(normalized, start=1):
            salt = secrets.token_bytes(16).hex()
            records.append(
                (
                    f"RBK-{index:03d}",
                    lookup_hash(access_key),
                    salt,
                    password_hash(access_key, salt),
                    now,
                )
            )
        connection.executemany(
            """
            INSERT INTO access_keys(label, lookup_hash, salt, key_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            records,
        )
    return len(normalized)


def release_access_key(access_key: str) -> bool:
    if not KEY_PATTERN.fullmatch(access_key):
        raise KeyStoreError(400, "Enter a valid 9-digit access key.")

    with connect() as connection:
        row = connection.execute(
            "SELECT id FROM access_keys WHERE lookup_hash = ?",
            (lookup_hash(access_key),),
        ).fetchone()
        if not row:
            return False
        connection.execute(
            "UPDATE access_keys SET device_id = NULL, activated_at = NULL WHERE id = ?",
            (row["id"],),
        )
        connection.execute("DELETE FROM sessions WHERE key_id = ?", (row["id"],))
    return True


def key_counts() -> dict[str, int]:
    with connect() as connection:
        total = connection.execute("SELECT COUNT(*) AS value FROM access_keys").fetchone()["value"]
        bound = connection.execute(
            "SELECT COUNT(*) AS value FROM access_keys WHERE device_id IS NOT NULL"
        ).fetchone()["value"]
    return {"total": total, "bound": bound, "available": total - bound}
