"""
도메인 레지스트리 기반 공통 실행 엔진.
"""

from typing import Any, Dict

from backend.core.domain_models import DomainExecutionRequest
from backend.core.domain_registry import get_domain_config, resolve_domain_runner


def run_domain_engine(request: DomainExecutionRequest) -> Dict[str, Any]:
    """
    등록된 도메인 실행기를 사용해 분석을 수행한다.
    """

    config = get_domain_config(request.domain)
    runner = resolve_domain_runner(request.domain)
    result = runner(raw_data=request.raw_data, metadata=request.metadata)

    if not isinstance(result, dict):
        raise ValueError(f"domain runner must return dict: {request.domain}")

    result.setdefault("domain", request.domain)
    result.setdefault("domain_config", {})
    result["domain_config"] = {
        "title": config.get("title"),
        "version": config.get("version"),
        "input_kind": config.get("input_kind"),
        "ontology_dir": config.get("ontology_dir"),
        "prompt_dir": config.get("prompt_dir"),
        **result["domain_config"],
    }
    return result

