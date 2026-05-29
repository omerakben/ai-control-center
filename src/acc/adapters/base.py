from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class ScanContext:
    root: Path
    files: list[Path]


@dataclass
class ProviderRoot:
    provider: str
    path: Path


class ProviderAdapter(Protocol):
    id: str
    display_name: str

    def detect(self, ctx: ScanContext) -> list[ProviderRoot]: ...

    def normalize(self, ctx: ScanContext, root: ProviderRoot) -> dict: ...
