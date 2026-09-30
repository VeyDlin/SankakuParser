from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import os
import threading


@dataclass
class Tokens:
    access: str
    refresh: str
    username: str


class TokenStore:
    """Persists the session between runs: tokens plus the user name.

    Passwords are never stored. Signing out drops the tokens but remembers the
    name, so the next sign-in form can be prefilled.
    """

    def __init__(self, path: Path) -> None:
        self.path: Path = path
        # Each site tab reads and rewrites the same file from its own thread.
        self.lock: threading.Lock = threading.Lock()


    def load(self, site: str) -> Tokens | None:
        entry = self.read_all().get(site)
        if not isinstance(entry, dict):
            return None

        access = entry.get('access')
        if not isinstance(access, str) or not access:
            return None

        refresh = entry.get('refresh')
        username = entry.get('username')

        return Tokens(
            access=access,
            refresh=refresh if isinstance(refresh, str) else '',
            username=username if isinstance(username, str) else ''
        )


    def save(self, site: str, tokens: Tokens) -> None:
        with self.lock:
            data = self.read_all()
            data[site] = asdict(tokens)
            self.write_all(data)


    def clear(self, site: str) -> None:
        """Drops the site's tokens, keeping the remembered user name."""
        with self.lock:
            data = self.read_all()
            entry = data.get(site)
            if entry is None:
                return

            username = entry.get('username') if isinstance(entry, dict) else None
            if isinstance(username, str) and username:
                data[site] = {'username': username}
            else:
                del data[site]

            self.write_all(data)


    def remembered_username(self, site: str) -> str:
        entry = self.read_all().get(site)
        username = entry.get('username') if isinstance(entry, dict) else None

        return username if isinstance(username, str) else ''


    def read_all(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}

        try:
            with self.path.open('r', encoding='utf-8') as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(data, dict):
            return {}

        return data


    def write_all(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self.path.open('w', encoding='utf-8') as file:
            json.dump(data, file, indent=4)

        # Tokens grant full account access, so keep the file owner-only wherever
        # the platform honours POSIX permissions.
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
