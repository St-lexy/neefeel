"""
Neefeel Core Domain Models & Schemas.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class Department(str, Enum):
    PRODUCT = "product"
    DESIGN = "design"
    ENGINEERING = "engineering"
    GROWTH = "growth"
    LEGAL = "legal"
    FINANCE = "finance"
    PEOPLE = "people"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED_ON_HITL = "blocked_on_hitl"
    BLOCKED_ON_DEPENDENCY = "blocked_on_dependency"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskResult(BaseModel):
    task_id: str
    department: Department
    status: str
    output: str
    artifacts: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    data: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("artifacts", "risks", mode="before")
    @classmethod
    def coerce_none_to_list(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value if v is not None]
        return [str(value)]

    @field_validator("data", mode="before")
    @classmethod
    def coerce_none_to_dict(cls, value: Any) -> Dict[str, Any]:
        if value is None or not isinstance(value, dict):
            return {}
        return value


class StructuredTask(BaseModel):
    task_id: str
    department: Department
    title: str
    instruction: str
    depends_on: List[str] = Field(default_factory=list)
    requires_human_confirmation: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    # Engineering only: True -> run the code builder, False -> documents only,
    # None -> fall back to a whole-word heuristic on title/instruction.
    should_build: Optional[bool] = None
    status: TaskStatus = TaskStatus.PENDING


class DecompositionPlan(BaseModel):
    founder_prompt: str
    summary: str
    tasks: List[StructuredTask] = Field(min_length=1)


class ConflictReport(BaseModel):
    task_ids: List[str] = Field(default_factory=list)
    departments: List[Department] = Field(default_factory=list)
    summary: str = Field(default="")
    resolution_proposal: str = Field(default="")


class ExecutiveBriefing(BaseModel):
    strategy_summary: str
    deliverables: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    pending_confirmations: List[str] = Field(default_factory=list)
    preview_url: Optional[str] = None


class CofounderDialogueResponse(BaseModel):
    intent: Literal["conversational_inquiry", "ready_for_execution"] = Field(
        description="Select 'conversational_inquiry' when brainstorming. Select 'ready_for_execution' when prompt is specific enough to build a task DAG."
    )
    reply: str = Field(
        description="Sharp, candid co-founder response."
    )
    missing_information: List[str] = Field(
        default_factory=list,
        description="Key unknowns."
    )
    recalled_facts: List[str] = Field(
        default_factory=list,
        description="Contextual facts or decisions recalled from previous conversation turns."
    )
    execution_brief: str = Field(
        default="",
        description="Self-contained directive for the planning engine. Required when intent is 'ready_for_execution'."
    )


class GeneratedFile(BaseModel):
    path: str = Field(description="Relative path of the file, e.g. 'index.html'.")
    content: str = Field(description="Source content for this file.")


class GeneratedProject(BaseModel):
    project_name: str = Field(description="Identifier or slug of the project directory.")
    summary: str = Field(default="Generated project prototype", description="Brief summary of what was generated.")
    files: List[GeneratedFile] = Field(default_factory=list, description="All files composing this generated project.")