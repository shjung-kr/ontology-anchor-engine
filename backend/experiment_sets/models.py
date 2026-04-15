from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ExperimentGoal = Literal[
    "mechanism_identification",
    "artifact_rejection",
    "parameter_sensitivity",
    "model_validation",
    "next_experiment_planning",
]

DecisionStatus = Literal["draft", "in_progress", "supported", "rejected", "inconclusive"]


class ExperimentRunLink(BaseModel):
    run_id: str
    sample_id: Optional[str] = None
    replicate_group: Optional[str] = None
    condition_label: Optional[str] = None
    is_reference: bool = False
    notes: Optional[str] = None


class SetComparison(BaseModel):
    left_run_id: str
    right_run_id: str
    comparison_purpose: Optional[str] = None
    changed_variables: List[str] = Field(default_factory=list)
    observed_differences: List[str] = Field(default_factory=list)
    interpretation_delta: List[str] = Field(default_factory=list)
    decision_impact: Optional[str] = None


class ExperimentSet(BaseModel):
    set_id: str
    title: str
    experiment_goal: ExperimentGoal
    primary_question: str = ""
    hypotheses: List[str] = Field(default_factory=list)
    control_variables: List[str] = Field(default_factory=list)
    sweep_variables: List[str] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)
    runs: List[ExperimentRunLink] = Field(default_factory=list)
    comparison_pairs: List[SetComparison] = Field(default_factory=list)
    set_level_summary: str = ""
    decision_status: DecisionStatus = "draft"
    analysis_artifacts: Dict[str, Any] = Field(default_factory=dict)
    created_at_utc: str
    updated_at_utc: str


class ExperimentSetCreateRequest(BaseModel):
    title: str
    experiment_goal: ExperimentGoal
    primary_question: str = ""
    hypotheses: List[str] = Field(default_factory=list)
    control_variables: List[str] = Field(default_factory=list)
    sweep_variables: List[str] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)


class ExperimentSetUpdateRequest(BaseModel):
    title: Optional[str] = None
    experiment_goal: Optional[ExperimentGoal] = None
    primary_question: Optional[str] = None
    hypotheses: Optional[List[str]] = None
    control_variables: Optional[List[str]] = None
    sweep_variables: Optional[List[str]] = None
    success_criteria: Optional[List[str]] = None
    decision_status: Optional[DecisionStatus] = None


class ExperimentSetAddRunRequest(BaseModel):
    run_id: str
    sample_id: Optional[str] = None
    replicate_group: Optional[str] = None
    condition_label: Optional[str] = None
    is_reference: bool = False
    notes: Optional[str] = None

