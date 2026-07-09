from src.modeling.thesis import load_thesis, thesis_filename


def test_thesis_extended_fields_load(tmp_path):
    company_id = "NASDAQ:LULU"
    (tmp_path / thesis_filename(company_id)).write_text(
        """
stage: work
analyst_status: legacy_refresh_required
thesis: Own a premium brand at a turnaround multiple.
investment_pillars:
  - Brand quality
  - International growth
variant_perception: Market prices maturity.
key_debate: Does product innovation offset saturation?
risks:
  - Product fatigue
swot:
  strengths:
    - Pricing power
  weaknesses:
    - Americas saturation
  opportunities:
    - China expansion
  threats:
    - Faster competitors
management_questions:
  - What changed in product velocity?
source:
  deck: LULU internal case
  as_of: 2025-11-06
  notes: Legacy deck; refresh before final view.
""".strip(),
        encoding="utf-8",
    )

    thesis = load_thesis(company_id, tmp_path)

    assert thesis.exists
    assert thesis.stage_label == "Active Work"
    assert thesis.analyst_status == "legacy_refresh_required"
    assert thesis.investment_pillars == ["Brand quality", "International growth"]
    assert thesis.swot["opportunities"] == ["China expansion"]
    assert thesis.management_questions == ["What changed in product velocity?"]
    assert thesis.source_deck == "LULU internal case"
    assert thesis.source_as_of == "2025-11-06"
