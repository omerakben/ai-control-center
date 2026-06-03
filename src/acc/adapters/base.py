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


# Human group headings for the doc buckets. Generator-controlled constants
# (never author input), so they are not html-escaped — same convention as the
# inventory typeLabel set by make_item.
_DOC_TYPE_LABELS = {
    "prds": "PRD",
    "adrs": "ADR",
    "decisions": "Decision",
    "workflows": "Workflow",
    "references": "Reference",
}


def doc_type_label(bucket: str) -> str:
    """Map a doc bucket key to its human group heading.

    Unknown buckets fall back to a title-cased key so a future bucket still
    gets a non-empty, deterministic label instead of an undefined group.
    """
    return _DOC_TYPE_LABELS.get(bucket, bucket.title())


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


def extract_metadata(fields: object) -> dict:
    """Filter and return safe metadata keys from parsed frontmatter."""
    metadata = {}
    if not isinstance(fields, dict):
        return metadata
    for k, v in fields.items():
        if k in ("name", "title", "description", "summary"):
            continue
        if isinstance(v, (str, bool, int, float)):
            metadata[k] = v
        elif isinstance(v, list) and all(isinstance(x, (str, bool, int, float)) for x in v):
            metadata[k] = v
    return metadata
