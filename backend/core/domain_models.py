"""
도메인 실행기와 레지스트리에서 사용하는 공통 모델 정의.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DomainExecutionRequest(BaseModel):
    """
    도메인 실행 요청 페이로드를 표현한다.
    """

    domain: str = Field(default="iv", description="실행할 도메인 식별자")
    raw_data: str = Field(description="분석할 원시 데이터")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="선택적 메타데이터")


class DomainSummary(BaseModel):
    """
    등록된 도메인의 요약 정보를 표현한다.
    """

    domain: str
    title: str
    description: str
    version: str
    input_kind: str
    runner: str
    ontology_dir: Optional[str] = None
    prompt_dir: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

