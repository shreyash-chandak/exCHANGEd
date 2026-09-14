"""Export one JSON schema per contract model to schemas/ (guide step 2.2)."""

import json
from pathlib import Path

from change.contracts import EXPORTED_MODELS

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"


def main() -> None:
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    for model in EXPORTED_MODELS:
        schema = model.model_json_schema()
        out_path = SCHEMAS_DIR / f"{model.__name__}.json"
        out_path.write_text(json.dumps(schema, indent=2) + "\n")
        print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
