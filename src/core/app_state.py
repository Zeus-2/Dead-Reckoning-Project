"""Small state file so my toolkit remembers the last folders I used."""

import json
from pathlib import Path

from src.core.settings import STATE_FILE


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(state):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(state, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # I deliberately keep state persistence non-critical.
        pass


def remember_path(key, path):
    state = load_state()
    state[key] = str(Path(path))
    save_state(state)


def remembered_path(key):
    value = load_state().get(key)

    if not value:
        return None

    path = Path(value)
    return path if path.exists() else None
