"""Append-only JSONL storage for contract models (guide step 2.3).

One file per model type per run: runs/<run_id>/<ModelName>.jsonl.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import TypeVar

import orjson
from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class JsonlStore:
    """JSONL store rooted at a single run directory."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def _file_for(self, model_cls: type[BaseModel]) -> Path:
        return self.path / f"{model_cls.__name__}.jsonl"

    def append(self, model: BaseModel) -> None:
        """Append one record. One write() call per line for atomicity."""
        file_path = self._file_for(type(model))
        line = orjson.dumps(model.model_dump(mode="json")) + b"\n"
        with open(file_path, "ab") as f:
            f.write(line)
            f.flush()

    def iter(self, model_cls: type[ModelT]) -> Iterator[ModelT]:
        """Yield records of the given model type in append order."""
        file_path = self._file_for(model_cls)
        if not file_path.exists():
            return
        with open(file_path, "rb") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                yield model_cls.model_validate(orjson.loads(raw_line))

    def read_all(self, model_cls: type[ModelT]) -> list[ModelT]:
        return list(self.iter(model_cls))
