"""Load optional settings from ``backend/.env`` once (real environment variables win).

Import this module before reading configuration with ``os.getenv``.
"""

import os

try:  # python-dotenv ships with the MCP SDK; the file itself is optional.
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=False)
except Exception:  # pragma: no cover - dotenv missing or unreadable file
    pass
