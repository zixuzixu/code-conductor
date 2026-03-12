"""Session lifecycle management — CRUD and metadata persistence."""

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

import structlog

from conductor.core.constants import SESSIONS_DIR
from conductor.core.models import Session

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


def _session_dir(session_id: UUID) -> Path:
    return SESSIONS_DIR / str(session_id)


def _metadata_path(session_id: UUID) -> Path:
    return _session_dir(session_id) / "metadata.json"


class SessionManager:
    """Manages Session CRUD and metadata persistence to JSON files.

    Each session is stored as ~/.code-conductor/sessions/{session_id}/metadata.json.
    """

    def create_session(
        self,
        name: str,
        repo_path: str | None = None,
        repo_url: str | None = None,
        base_branch: str = "main",
        max_workers: int = 3,
    ) -> Session:
        session = Session(
            name=name,
            repo_path=repo_path,
            repo_url=repo_url,
            base_branch=base_branch,
            max_workers=max_workers,
        )
        session_dir = _session_dir(session.id)
        session_dir.mkdir(parents=True, exist_ok=True)
        self._save(session)
        logger.info("session_created", session_id=str(session.id), name=name)
        return session

    def get_session(self, session_id: UUID) -> Session | None:
        path = _metadata_path(session_id)
        if not path.exists():
            return None
        with open(path) as f:
            data = json.load(f)
        return Session(**data)

    def list_sessions(self) -> list[Session]:
        sessions = []
        if not SESSIONS_DIR.exists():
            return sessions
        for entry in sorted(SESSIONS_DIR.iterdir()):
            meta = entry / "metadata.json"
            if meta.exists():
                with open(meta) as f:
                    data = json.load(f)
                sessions.append(Session(**data))
        return sessions

    def update_session(self, session: Session) -> Session:
        session.updated_at = datetime.now()
        self._save(session)
        return session

    def delete_session(self, session_id: UUID) -> bool:
        session_dir = _session_dir(session_id)
        if not session_dir.exists():
            return False
        # Remove all files in the session directory
        import shutil

        shutil.rmtree(session_dir)
        logger.info("session_deleted", session_id=str(session_id))
        return True

    def scan_projects(self, dirs: list[str]) -> list[dict[str, str]]:
        """Scan directories for git repositories.

        Returns list of {name, path} dicts for directories containing .git/.
        """
        repos = []
        for dir_path in dirs:
            base = Path(dir_path).expanduser().resolve()
            if not base.is_dir():
                continue
            for entry in sorted(base.iterdir()):
                if entry.is_dir() and (entry / ".git").is_dir():
                    repos.append({"name": entry.name, "path": str(entry)})
        return repos

    def _save(self, session: Session) -> None:
        path = _metadata_path(session.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = session.model_dump(mode="json")
        # Atomic write: write to temp then rename
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        tmp.replace(path)
