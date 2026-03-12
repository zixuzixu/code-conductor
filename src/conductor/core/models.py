"""Pydantic v2 data models for Code Conductor."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from conductor.core.constants import Priority, SessionStatus, TaskStatus, ThreadStatus

# --- Task ---


class Task(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str = ""
    priority: Priority = Priority.P1
    status: TaskStatus = TaskStatus.QUEUED
    thread_id: UUID | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    retry_count: int = 0
    error_context: str | None = None
    parent_task_id: UUID | None = None  # for follow-up fix tasks


# --- Thread ---


class Thread(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    task_id: UUID | None = None
    status: ThreadStatus = ThreadStatus.PENDING
    branch_name: str | None = None
    worktree_path: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    exit_code: int | None = None
    summary: str | None = None  # Master Agent's review summary


# --- Session ---


class Session(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    repo_path: str | None = None
    repo_url: str | None = None
    base_branch: str = "main"
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    max_workers: int = 3
    conversation_history: list[dict] = Field(default_factory=list)


# --- Configuration ---


class LLMProviderConfig(BaseModel):
    provider: str  # "gemini", "kimi"
    model: str
    api_key: str = ""
    base_url: str | None = None
    max_tokens: int = 8192
    temperature: float = 0.7


class ConductorConfig(BaseModel):
    primary_llm: LLMProviderConfig = Field(
        default_factory=lambda: LLMProviderConfig(provider="gemini", model="gemini-3.1-pro-preview")
    )
    fallback_llm: LLMProviderConfig = Field(
        default_factory=lambda: LLMProviderConfig(provider="kimi", model="kimi-k2.5")
    )
    project_dirs: list[str] = Field(default_factory=list)
    max_workers_per_session: int = 3
    backup_retention_hours: int = 168  # 7 days
