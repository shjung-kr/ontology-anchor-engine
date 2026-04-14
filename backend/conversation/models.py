"""
Pydantic models for conversational intent capture.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


QuestionCategory = Literal["missing_condition_check", "competing_proposal_disambiguation", "assumption_confirmation"]
AnswerKind = Literal["single_select", "multi_select", "confirm", "reject", "approve", "deprioritize", "unknown", "text"]
AssumptionState = Literal["pending", "confirmed", "rejected", "approved"]


class IntentUpdate(BaseModel):
    analysis_priority: Optional[
        Literal["mechanism_identification", "measurement_anomaly_diagnosis", "next_experiment_planning"]
    ] = None
    focus_claims: List[str] = Field(default_factory=list)
    exclude_claims: List[str] = Field(default_factory=list)
    keep_open_claims: List[str] = Field(default_factory=list)
    confirmed_conditions: Dict[str, Any] = Field(default_factory=dict)
    uncertain_conditions: List[str] = Field(default_factory=list)
    confirmed_assumptions: List[str] = Field(default_factory=list)
    rejected_assumptions: List[str] = Field(default_factory=list)
    approved_claims: List[str] = Field(default_factory=list)
    approved_assumptions: List[str] = Field(default_factory=list)
    note: Optional[str] = None


class ChatTurnRequest(BaseModel):
    run_id: str
    user_text: str = Field(default="", description="Free-form user message captured for the run log.")
    intent_update: IntentUpdate = Field(default_factory=IntentUpdate)
    structured_answers: List["StructuredAnswer"] = Field(default_factory=list)


class DomainChatQuestion(BaseModel):
    question_id: str
    category: QuestionCategory
    prompt: str
    reason: str
    target_ids: List[str] = Field(default_factory=list)
    expected_answer_kind: AnswerKind = "text"
    options: List[Dict[str, str]] = Field(default_factory=list)


class StructuredAnswer(BaseModel):
    question_id: str
    category: Optional[QuestionCategory] = None
    answer_kind: AnswerKind
    selected_ids: List[str] = Field(default_factory=list)
    condition_updates: Dict[str, Any] = Field(default_factory=dict)
    note: Optional[str] = None
    approve_for_overlay: bool = False


class OverlayReviewDecisionRequest(BaseModel):
    overlay_type: Literal["claim", "assumption", "measurement_condition"]
    target_id: str
    decision: Literal["approved", "rejected"]
    note: Optional[str] = None


ChatTurnRequest.model_rebuild()
