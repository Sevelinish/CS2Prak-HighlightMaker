from __future__ import annotations

from pathlib import Path

HISTORY_FILE_NAME = "shell_history.txt"
DEFAULT_LIMIT = 200


class CommandHistory:
    def __init__(self, path: Path | None = None, limit: int = DEFAULT_LIMIT) -> None:
        self._path = path
        self._limit = max(1, limit)
        self._entries: list[str] = self._load()
        self._index = 0
        self._draft = ""

    @property
    def entries(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def remember(self, line: str) -> None:
        cleaned = line.strip()
        self.reset()
        if not cleaned:
            return
        if self._entries and self._entries[-1] == cleaned:
            return
        self._entries.append(cleaned)
        del self._entries[: max(0, len(self._entries) - self._limit)]
        self._save()

    def reset(self) -> None:
        self._index = 0
        self._draft = ""

    def previous(self, draft: str) -> str | None:
        if self._index >= len(self._entries):
            return None
        if self._index == 0:
            self._draft = draft
        self._index += 1
        return self._entries[-self._index]

    def following(self) -> str | None:
        if self._index == 0:
            return None
        self._index -= 1
        if self._index == 0:
            return self._draft
        return self._entries[-self._index]

    def suggest(self, prefix: str) -> str:
        if not prefix:
            return ""
        for entry in reversed(self._entries):
            if entry.startswith(prefix) and len(entry) > len(prefix):
                return entry[len(prefix) :]
        return ""

    def _load(self) -> list[str]:
        if self._path is None or not self._path.is_file():
            return []
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        return [line.strip() for line in lines if line.strip()][-self._limit :]

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text("\n".join(self._entries) + "\n", encoding="utf-8")
        except OSError:
            return
