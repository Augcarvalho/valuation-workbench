"""Analyst thesis layer.

A thesis is the human half of the system: investment pillars, variant
perception, key debate, catalysts, risks, SWOT, source metadata, and a dated
journal, stored as one YAML file per company. Private theses live in
``data_private/theses/`` (never committed); the public demo ships sample
theses under ``data/sample/theses/``.

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
    analyst_status: str = ""
    thesis: str = ""
    investment_pillars: list[str] = field(default_factory=list)
    variant_perception: str = ""
    key_debate: str = ""
    catalysts: list[dict] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    swot: dict[str, list[str]] = field(default_factory=dict)
    management_questions: list[str] = field(default_factory=list)
    scenarios: dict = field(default_factory=dict)
    journal: list[dict] = field(default_factory=list)
    source_deck: str = ""
    source_as_of: str = ""
    source_notes: str = ""
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


def _clean_list(values) -> list[str]:
    return [_clean_str(v) for v in (values or []) if _clean_str(v)]


def _clean_swot(raw) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for key in ("strengths", "weaknesses", "opportunities", "threats"):
        out[key] = _clean_list(raw.get(key))
    return {k: v for k, v in out.items() if v}


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
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    questions = raw.get("management_questions") or raw.get("key_questions_for_management") or []
    return Thesis(
        company_id=company_id,
        stage=stage if stage in STAGES else "watch",
        analyst_status=_clean_str(raw.get("analyst_status")),
        thesis=_clean_str(raw.get("thesis")),
        investment_pillars=_clean_list(raw.get("investment_pillars")),
        variant_perception=_clean_str(raw.get("variant_perception")),
        key_debate=_clean_str(raw.get("key_debate")),
        catalysts=[c for c in (raw.get("catalysts") or []) if isinstance(c, dict)],
        risks=_clean_list(raw.get("risks")),
        swot=_clean_swot(raw.get("swot")),
        management_questions=_clean_list(questions),
        scenarios=raw.get("scenarios") or {},
        journal=[j for j in (raw.get("journal") or []) if isinstance(j, dict)],
        source_deck=_clean_str(raw.get("source_deck") or source.get("deck")),
        source_as_of=_clean_str(raw.get("source_as_of") or source.get("as_of")),
        source_notes=_clean_str(raw.get("source_notes") or source.get("notes")),
        path=path,
    )


def list_theses(theses_dir: Path) -> list[str]:
    """Company ids (de-sanitized best effort) that have a thesis file."""
    if theses_dir is None or not Path(theses_dir).exists():
        return []
    return sorted(p.stem for p in Path(theses_dir).glob("*.yaml"))
