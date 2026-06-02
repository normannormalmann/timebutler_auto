"""
Credential handling for the Timebutler automation.

Password resolution order:
1. --password CLI argument (debugging escape hatch)
2. Windows Credential Manager (via keyring, service "timebutler")
3. TIMEBUTLER_PASSWORD from the environment / .env file (fallback)

When a password is found in the environment and keyring is available, it is
migrated into the Credential Manager and removed from the .env file. The
credential store must never block a punch-in: every keyring failure degrades
to the .env value with a warning.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore

try:
    import keyring
except ImportError:  # pragma: no cover - optional dependency
    keyring = None  # type: ignore

SERVICE_NAME = "timebutler"


def get_stored_password(username: str, logger) -> Optional[str]:
    if keyring is None:
        return None
    try:
        return keyring.get_password(SERVICE_NAME, username)
    except Exception as exc:
        logger.warning("Credential Manager unavailable: %s", exc)
        return None


def store_password(username: str, password: str, logger) -> bool:
    if keyring is None:
        return False
    try:
        keyring.set_password(SERVICE_NAME, username, password)
        return True
    except Exception as exc:
        logger.warning("Could not store password in Credential Manager: %s", exc)
        return False


def remove_password_from_env_file(env_path: Path, logger) -> None:
    """Rewrites the .env file without its TIMEBUTLER_PASSWORD line."""
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
        kept = [ln for ln in lines if not ln.strip().startswith("TIMEBUTLER_PASSWORD")]
        if len(kept) == len(lines):
            return
        content = "\n".join(kept)
        if content:
            content += "\n"
        env_path.write_text(content, encoding="utf-8")
        logger.info("Removed TIMEBUTLER_PASSWORD from %s.", env_path)
    except OSError as exc:
        logger.warning("Could not rewrite %s: %s", env_path, exc)


def migrate_env_password(env_path: Path, username: str, env_password: str, logger) -> None:
    """Moves a password found in the environment into the Credential Manager."""
    stored = get_stored_password(username, logger)
    if stored == env_password:
        # already migrated earlier; just clean up the .env leftover
        remove_password_from_env_file(env_path, logger)
        return
    if store_password(username, env_password, logger):
        logger.info(
            "Migrated password for '%s' into the Windows Credential Manager.", username
        )
        remove_password_from_env_file(env_path, logger)


def load_credentials(args, base_dir: Path, logger) -> Tuple[Optional[str], Optional[str]]:
    """Returns (username, password); either is None when unresolvable."""
    env_path = base_dir / ".env"
    if load_dotenv is not None:
        load_dotenv(env_path, encoding="utf-8-sig")

    username = args.username or os.getenv("TIMEBUTLER_USERNAME")
    if not username:
        return None, None

    if args.password:
        return username, args.password

    env_password = os.getenv("TIMEBUTLER_PASSWORD")
    if env_password and keyring is not None:
        migrate_env_password(env_path, username, env_password, logger)

    password = get_stored_password(username, logger) or env_password
    return username, password
