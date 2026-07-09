# GitHub Portfolio Strategy

This project is built to demonstrate institutional finance judgment without
publishing licensed Capital IQ data or the private watchlist.

## What can be public

- Source code under `src/`, `scripts/`, and `tests/`.
- Public demo data under `data/sample/`.
- Public templates under `data/templates/`.
- Public documentation under `docs/`.
- Sample outputs in `reports/sample/` generated from the public demo only.
- Sanitized screenshots that do not show licensed CapIQ figures, private
  tickers, private peer sets, or local file paths.

## What must stay private

- `data_private/` and everything below it.
- Raw Capital IQ Excel exports, CSV exports, screenshots, and downloaded files.
- Analyst thesis YAML files for real companies.
- Valuation assumption YAML files for real companies.
- Generated private IC memos, valuation cases, board packs, and visual QA files.
- Original case-study decks if they include Capital IQ financials, consensus,
  multiples, screenshots, or other licensed data.

## How to describe the project publicly

Use language that emphasizes the workflow, not the proprietary dataset:

> Built a private Capital IQ-powered valuation workbench that converts company
> financial exports, peer sets, analyst-written thesis files, and DCF assumptions
> into data-audited dashboards, valuation cases, and IC-style memo outputs. The
> public GitHub repo includes a fully offline demo and confidentiality guardrails;
> licensed data and private theses stay outside version control.

## Case-study thesis workflow

The system supports a clean split between the public code and the private
analyst view:

1. Build or import an investment thesis into `data_private/theses/<company_id>.yaml`.
2. Put DCF assumptions into `data_private/assumptions/<company_id>.yaml`.
3. Refresh Capital IQ exports locally.
4. Run the dashboard or export an IC memo/valuation case.
5. Publish only sanitized public-demo outputs or redacted screenshots.

The thesis file captures the human work that automation cannot replace:

- Investment pillars.
- Variant perception.
- Key debate.
- Catalysts.
- Risks.
- SWOT.
- Management questions.
- Source/as-of metadata.
- Dated journal entries.

## Publication checklist

Before pushing to GitHub:

```powershell
git status --short
git check-ignore data_private/theses/example.yaml
git check-ignore data_private/reports/private_output.html
pytest tests/test_confidentiality.py tests/test_sample_outputs_safety.py
```

Also manually inspect:

- `README.md` for private company names or Capital IQ-derived figures.
- `reports/sample/` for private-mode markers.
- Screenshots for private tickers, local paths, or licensed data tables.
- Docs for pasted CapIQ formulas or proprietary mnemonics beyond template-level
  examples.

## Recruiter narrative

The strongest interview framing is:

> I had already built IB-style valuation cases manually in Excel and PowerPoint.
> I turned that process into software: Capital IQ refreshes the data, the system
> audits the inputs, maps the company to reviewed peers, builds valuation cases,
> and merges the machine layer with my analyst-written thesis. The key point is
> not automation for its own sake; it is making the investment process repeatable
> while still preserving human judgment.
