"""C3 structured hand-offs: agents exchange these Pydantic objects, never free text, for anything a later step
decides on."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class JobSpec(BaseModel):
    job_id: str
    title: str
    category: str = ""
    deliverables: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list, description="skills/tools the job needs, short phrases")
    budget: float | None = None
    timeline_weeks: float | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list, description="needs implied but not stated")
    complexity: int = Field(2, ge=1, le=5)
    vague: bool = False


class RiskReport(BaseModel):
    score: float = Field(ge=0, le=1, description="0 safe .. 1 certainly harmful")
    scam: bool = False
    flags: list[str] = Field(default_factory=list)
    injection_hits: list[str] = Field(default_factory=list)
    client_quality: float = Field(0.5, ge=0, le=1)
    explanation: str = ""


class RequirementMatch(BaseModel):
    requirement: str
    covered: bool
    evidence_ids: list[str] = Field(default_factory=list)
    note: str = ""


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matches: list[RequirementMatch] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class BidDecision(BaseModel):
    action: Literal["bid", "watch", "skip"]
    reason: str
    auto: bool = True


class PriceQuote(BaseModel):
    amount: float
    currency: str = "USD"
    market: dict = Field(default_factory=dict)
    connects_cost: int = 0
    connects_balance: int | None = None
    connects_worth_it: bool = True
    rationale: str = ""


class Citation(BaseModel):
    sentence: str
    evidence_ids: list[str] = Field(default_factory=list)


class ProposalDraft(BaseModel):
    cover_letter: str
    screening_answers: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    version: int = 1


class Critique(BaseModel):
    approve: bool
    issues: list[str] = Field(default_factory=list)
    grounding: int = Field(3, ge=1, le=5)
    personalisation: int = Field(3, ge=1, le=5)
    length_ok: bool = True


class Violation(BaseModel):
    rule_id: str
    text: str


class ComplianceVerdict(BaseModel):
    passed: bool
    blocked: bool = False
    violations: list[Violation] = Field(default_factory=list)
    reason: str = ""
    cleaned_text: str = ""


class ApprovalDecision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = None
    reason: str | None = None


class ReplyIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "hire", "scam_signal", "other"]
    summary: str = ""
    injection_hits: list[str] = Field(default_factory=list)


class ReplyDraft(BaseModel):
    text: str
    proposed_slots: list[str] = Field(default_factory=list)
