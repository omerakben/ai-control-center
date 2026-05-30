from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..ids import stable_id


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


_INV_BUCKETS = ("agents", "skills", "hooks", "commands", "mcpServers", "rules")
_DOC_BUCKETS = ("prds", "adrs", "decisions", "workflows", "references")


def empty_inventory() -> dict:
    return {k: [] for k in _INV_BUCKETS}


def empty_docs() -> dict:
    return {k: [] for k in _DOC_BUCKETS}


def make_item(provider: str, kind: str, type_label: str,
              title: str, path: str, summary: str) -> dict:
    return {
        "id": stable_id(provider, kind, path, title),
        "provider": provider,
        "type": kind,
        "typeLabel": type_label,
        "title": title,
        "path": path,
        "summary": summary,
    }
