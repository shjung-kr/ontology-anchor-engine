import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ONTO = ROOT / "backend" / "ontology"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def schema_enum(name: str):
    data = load_json(ONTO / "schema" / name)
    return set(data.get("enum", []))


def main() -> int:
    errors = []
    valid_conditions = schema_enum("measurement_conditions.schema.json")
    valid_mechanisms = schema_enum("electrical_mechanisms.schema.json")
    valid_claims = schema_enum("claim_concepts.schema.json")
    valid_assumptions = schema_enum("assumptions.schema.json")

    for path in sorted((ONTO / "04_scientific_justification").glob("*.json")):
        sj = load_json(path)["scientific_justification"]
        if sj.get("claim_concept") not in valid_claims:
            errors.append(f"{path.name}: invalid claim_concept {sj.get('claim_concept')}")
        for item in sj.get("measurement_conditions", []):
            if item not in valid_conditions:
                errors.append(f"{path.name}: invalid measurement_condition {item}")
        for item in sj.get("assumptions", []):
            if item not in valid_assumptions:
                errors.append(f"{path.name}: invalid assumption {item}")
        for regime in sj.get("mechanism_by_regime", []):
            for mech in regime.get("mechanisms", []):
                if mech not in valid_mechanisms:
                    errors.append(f"{path.name}: invalid mechanism {mech}")

    if errors:
        for error in errors:
            print(error)
        return 1

    print("ontology validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
