"""
Configuration loader for SAP Datasphere credentials.

Reads from a .env file (KEY=VALUE format) and falls back to
OS environment variables.  No external dependencies.
"""

import os
from pathlib import Path

# Path to the .env file relative to this module
_ENV_FILE = Path(__file__).parent / ".env"

# Required configuration keys
REQUIRED_KEYS = [
    "DSP_TENANT_URL",
    "DSP_CLIENT_ID",
    "DSP_CLIENT_SECRET",
    "DSP_TOKEN_URL",
]


def _load_env_file(path: Path) -> dict[str, str]:
    """
    Parse a .env file into a dict.
    Ignores blank lines and comments (#).
    """
    env: dict[str, str] = {}
    if not path.exists():
        return env

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def load_config() -> dict[str, str]:
    """
    Load configuration: .env file values take precedence,
    then OS environment variables are used as fallback.

    Raises ValueError if any required key is missing.
    """
    # Load .env file first
    file_env = _load_env_file(_ENV_FILE)

    # Merge: .env file > OS env
    config: dict[str, str] = {}
    all_keys = REQUIRED_KEYS + ["DSP_AUTH_URL", "DSP_USER_ID"]

    for key in all_keys:
        value = file_env.get(key) or os.environ.get(key, "")
        if value:
            config[key] = value

    # Validate required keys
    missing = [k for k in REQUIRED_KEYS if k not in config]
    if missing:
        raise ValueError(
            f"Missing required configuration: {missing}\n"
            f"Create a .env file from .env.example or set environment variables."
        )

    return config
