"""Request/response models (the TypeScript client in apps/web/src/lib/api is generated from these via OpenAPI)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=6, max_length=100)


class TokenOut(BaseModel):
    token: str
    user: "UserOut"


class Prefs(BaseModel):
    rate_floor: float = 40
    connects_weekly_budget: int = 120
    saved_searches: list[str] = Field(default_factory=lambda: [""])
    categories: list[str] = Field(default_factory=list)
    min_budget: float = 0
    autonomy: Literal["suggest_only", "auto_skip_low_fit"] = "auto_skip_low_fit"
    marketplace: Literal["gigsim", "upwork_live"] = "gigsim"


class UserOut(BaseModel):
    id: str
    username: str
    owner: str | None
    prefs: Prefs


class Onboarding(BaseModel):
    persona: Literal["ai_ml", "fullstack", "data_analyst", "own"]
    prefs: Prefs


class JobRow(BaseModel):
    job_id: str
    title: str
    status: str
    thread_id: str | None = None
    fit: float | None = None
    risk: float | None = None
    scam: bool | None = None
    flags: list[str] = Field(default_factory=list)
    action: str | None = None
    reason: str | None = None
    price: float | None = None
    connects_cost: int | None = None
    budget: float | None = None
    marketplace_status: str | None = None
    updated_at: float | None = None


class JobDetail(BaseModel):
    job: dict[str, Any]
    status: str
    thread_id: str | None
    state: dict[str, Any]
    pending_approval: dict[str, Any] | None = None


class ApprovalIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = None
    reason: str | None = None


class RegenerateIn(BaseModel):
    paragraph_index: int
    instruction: str = ""


class RunRow(BaseModel):
    id: str
    kind: str
    thread_id: str | None
    ref_id: str | None
    status: str | None
    trace_id: str | None
    created_at: float
    tokens: int | None = None
    cost_usd: float | None = None
    latency_s: float | None = None
    trace_url: str | None = None


class TaskOut(BaseModel):
    queued: bool
    task_id: int | None = None
    message: str = ""


class MemoryItem(BaseModel):
    namespace: str
    key: str
    value: dict[str, Any]


class Health(BaseModel):
    api: bool
    marketplace: bool
    portfolio: bool
    workspace: bool
    degraded: bool
    mode: str


TokenOut.model_rebuild()
