"""Environment variable utilities for loading secrets from KeePassXC."""

import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from .logging import logger

KEEPASS_DB_PATH = Path.home() / ".secrets" / "env_vars.kdbx"


def _get_keepass_password() -> str | None:
    """Get the KeePass database password from the system keyring."""
    logger.debug("Getting KeePass password from keyring")
    try:
        result = subprocess.run(
            ["secret-tool", "lookup", "service", "keepass_env"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        logger.debug(f"secret-tool returncode: {result.returncode}")
        if result.returncode == 0:
            logger.debug("Got password from keyring")
            return result.stdout.strip()
        logger.error(f"secret-tool failed: {result.stderr}")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        logger.error(f"secret-tool exception: {e}")
    return None


def _export_keepass_xml(db_path: Path, password: str) -> str | None:
    """Export KeePass database to XML."""
    logger.debug(f"Exporting KeePass database: {db_path}")
    try:
        result = subprocess.run(
            [
                "flatpak",
                "run",
                "--command=keepassxc-cli",
                "org.keepassxc.KeePassXC",
                "export",
                "-f",
                "xml",
                str(db_path),
            ],
            input=password,
            capture_output=True,
            text=True,
            timeout=30,
        )
        logger.debug(f"keepassxc-cli returncode: {result.returncode}")
        if result.returncode == 0:
            logger.debug(f"Exported {len(result.stdout)} bytes of XML")
            return result.stdout
        logger.error(f"keepassxc-cli failed: {result.stderr}")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        logger.error(f"keepassxc-cli exception: {e}")
    return None


def _parse_keepass_entries(xml_content: str) -> dict[str, str]:
    """Parse KeePass XML and extract Title -> Password mappings."""
    entries: dict[str, str] = {}
    try:
        root = ET.fromstring(xml_content)
        for entry in root.findall(".//Group/Entry"):
            title = None
            password = None
            for string_node in entry.findall("String"):
                key = string_node.find("Key")
                value = string_node.find("Value")
                if key is not None and value is not None:
                    if key.text == "Title":
                        title = value.text
                    elif key.text == "Password":
                        password = value.text
            if title and password:
                entries[title] = password
    except ET.ParseError:
        pass
    return entries


_cached_entries: dict[str, str] | None = None
_last_error: str | None = None


def get_last_error() -> str | None:
    """Get the last error message from credential loading."""
    return _last_error


def get_keepass_entries() -> dict[str, str]:
    """Get all entries from KeePass database (cached)."""
    global _cached_entries, _last_error
    if _cached_entries is not None:
        return _cached_entries

    password = _get_keepass_password()
    if not password:
        _last_error = "Failed to get KeePass password from keyring"
        return {}

    xml_content = _export_keepass_xml(KEEPASS_DB_PATH, password)
    if not xml_content:
        _last_error = "Failed to export KeePass database"
        return {}

    _cached_entries = _parse_keepass_entries(xml_content)
    if not _cached_entries:
        _last_error = "No entries found in KeePass database"
    return _cached_entries


def get_env_var(name: str) -> str | None:
    """
    Get an environment variable, falling back to KeePass.

    First checks os.environ, then KeePass database.
    """
    # First try the current environment
    value = os.environ.get(name)
    if value:
        return value

    # Fall back to KeePass
    entries = get_keepass_entries()
    return entries.get(name)


def get_telegram_credentials() -> tuple[str | None, str | None]:
    """Get Telegram bot token and chat ID."""
    logger.debug("Getting Telegram credentials")
    token = get_env_var("TELEGRAM_PERSONAL_BOT_TOKEN")
    chat_id = get_env_var("TELEGRAM_PERSONAL_BOT_CHAT_ID")
    logger.debug(f"Token: {bool(token)}, ChatID: {bool(chat_id)}")
    return token, chat_id
