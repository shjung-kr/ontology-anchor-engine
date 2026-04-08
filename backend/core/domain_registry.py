"""
도메인 레지스트리 로더와 실행기 해석 유틸리티.
"""

import importlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List

from backend.core.domain_models import DomainSummary

ROOT_DIR = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT_DIR / "backend" / "domain_registry.json"


def _read_registry_payload() -> Dict[str, Any]:
    """
    레지스트리 JSON 파일을 읽어 사전으로 반환한다.
    """

    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def load_domain_registry() -> Dict[str, Any]:
    """
    전체 도메인 레지스트리 원문을 반환한다.
    """

    return _read_registry_payload()


def list_domain_summaries() -> List[DomainSummary]:
    """
    등록된 도메인들의 요약 목록을 반환한다.
    """

    payload = _read_registry_payload()
    summaries: List[DomainSummary] = []

    for domain_id, config in sorted(payload.get("domains", {}).items()):
        summaries.append(
            DomainSummary(
                domain=domain_id,
                title=str(config.get("title") or domain_id),
                description=str(config.get("description") or ""),
                version=str(config.get("version") or "0.0.0"),
                input_kind=str(config.get("input_kind") or "raw_text"),
                runner=str(config.get("runner") or ""),
                ontology_dir=config.get("ontology_dir"),
                prompt_dir=config.get("prompt_dir"),
                tags=list(config.get("tags") or []),
            )
        )

    return summaries


def get_domain_config(domain: str) -> Dict[str, Any]:
    """
    특정 도메인의 설정을 반환한다.
    """

    payload = _read_registry_payload()
    config = payload.get("domains", {}).get(domain)
    if not isinstance(config, dict):
        raise KeyError(f"unknown domain: {domain}")
    return config


def resolve_domain_runner(domain: str) -> Callable[..., Dict[str, Any]]:
    """
    도메인 설정에 기록된 runner 경로를 실제 함수로 해석한다.
    """

    config = get_domain_config(domain)
    runner_path = str(config.get("runner") or "").strip()
    if ":" not in runner_path:
        raise ValueError(f"invalid runner path: {runner_path}")

    module_name, func_name = runner_path.split(":", 1)
    module = importlib.import_module(module_name)
    runner = getattr(module, func_name, None)
    if not callable(runner):
        raise ValueError(f"runner is not callable: {runner_path}")
    return runner

