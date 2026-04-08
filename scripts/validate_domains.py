"""
등록된 도메인과 domain pack 구성을 검증한다.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.domain_registry import get_domain_config, list_domain_summaries, resolve_domain_runner


def validate_domain(domain_id: str) -> list[str]:
    """
    단일 도메인의 registry와 pack 파일을 검증한다.
    """

    errors: list[str] = []
    config = get_domain_config(domain_id)

    try:
        resolve_domain_runner(domain_id)
    except Exception as exc:
        errors.append(f"{domain_id}: runner resolution failed: {exc}")

    ontology_dir = ROOT / str(config.get("ontology_dir") or "")
    if not ontology_dir.is_dir():
        errors.append(f"{domain_id}: ontology_dir not found: {ontology_dir}")

    pack_path = ontology_dir / "domain_pack.json"
    if not pack_path.is_file():
        errors.append(f"{domain_id}: missing domain pack file: {pack_path}")
        return errors

    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{domain_id}: failed to parse domain pack: {exc}")
        return errors

    if pack.get("domain") != domain_id:
        errors.append(f"{domain_id}: domain_pack domain mismatch: {pack.get('domain')}")

    namespaces = pack.get("ontology", {}).get("namespaces", [])
    for namespace in namespaces:
        namespace_path = ontology_dir / namespace
        if not namespace_path.exists():
            errors.append(f"{domain_id}: missing namespace: {namespace_path}")

    return errors


def main() -> int:
    """
    모든 등록 도메인에 대해 검증을 수행한다.
    """

    errors: list[str] = []
    for summary in list_domain_summaries():
        errors.extend(validate_domain(summary.domain))

    if errors:
        for error in errors:
            print(error)
        return 1

    print("domain validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
