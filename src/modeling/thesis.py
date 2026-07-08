"""Analyst thesis layer.

A thesis is the human half of the system: variant perception, key debate,
catalysts, risks, stage, and a dated journal, stored as one YAML file per
company. Private theses live in ``data_private/theses/`` (never committed);
the public demo ships sample theses under ``data/sample/theses/``.

File naming: ``<company_id>.yaml`` with ``:`` replaced by ``_`` because Windows
forbids colons in filenames (``BOVESPA:TOTS3`` -> ``BOVESPA_TOTS3.yaml``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

STAGES = ("watch", "work", "core", "pass")


@dataclass
class Thesis:
    company_id: str
    stage: str = "watch"
    thesis: str = ""
    variant_perception: str = ""
    key_debate: str = ""
    catalysts: list[dict] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    scenarios: dict = field(default_factory=dict)
    journal: list[dict] = field(default_factory=list)
    path: Path | None = None

    @property
    def exists(self) -> bool:
        return self.path is not None

    @property
    def stage_label(self) -> str:
        return {"watch": "Watch", "work": "Active Work", "core": "Core Position", "pass": "Pass"}.get(self.stage, self.stage.title())


def thesis_filename(company_id: str) -> str:
    return company_id.replace(":", "_") + ".yaml"


def _clean_str(value) -> str:
    return str(value).strip() if value is not None else ""


def load_thesis(company_id: str, theses_dir: Path) -> Thesis:
    """Load the thesis for a company, or an empty placeholder if none exists."""
    empty = Thesis(company_id=company_id)
    if theses_dir is None or not Path(theses_dir).exists():
        return empty
    path = Path(theses_dir) / thesis_filename(company_id)
    if not path.exists():
        return empty
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return empty

    stage = _clean_str(raw.get("stage", "watch")).lower()
    return Thesis(
        company_id=company_id,
        stage=stage if stage in STAGES else "watch",
        thesis=_clean_str(raw.get("thesis")),
        variant_perception=_clean_str(raw.get("variant_perception")),
        key_debate=_clean_str(raw.get("key_debate")),
        catalysts=[c for c in (raw.get("catalysts") or []) if isinstance(c, dict)],
        risks=[_clean_str(r) for r in (raw.get("risks") or []) if _clean_str(r)],
        scenarios=raw.get("scenarios") or {},
        journal=[j for j in (raw.get("journal") or []) if isinstance(j, dict)],
        path=path,
    )


def list_theses(theses_dir: Path) -> list[str]:
    """Company ids (de-sanitized best effort) that have a thesis file."""
    if theses_dir is None or not Path(theses_dir).exists():
        return []
    return sorted(p.stem for p in Path(theses_dir).glob("*.yaml"))
