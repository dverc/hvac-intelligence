from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


@dataclass
class CsvImportResult:
    total_rows: int
    imported: int
    skipped: int
    errors: list[dict[str, Any]]
    dry_run: bool
    warnings: list[str] = field(default_factory=list)


class CsvImportResultResponse(BaseModel):
    total_rows: int
    imported: int
    skipped: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    dry_run: bool
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_result(cls, result: CsvImportResult) -> CsvImportResultResponse:
        return cls(
            total_rows=result.total_rows,
            imported=result.imported,
            skipped=result.skipped,
            errors=result.errors,
            dry_run=result.dry_run,
            warnings=result.warnings,
        )
