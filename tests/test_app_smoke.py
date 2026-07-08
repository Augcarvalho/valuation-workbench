"""App wiring: every page module imports, and the router matches the nav."""

import importlib


PAGE_MODULES = [
    "watchlist", "compare", "situation", "peers", "consensus", "financials",
    "capital_structure", "valuation_case", "valuation_expectations",
    "ic_memo", "data_audit", "refresh",
]


def test_every_page_module_imports_and_exposes_render():
    for name in PAGE_MODULES:
        mod = importlib.import_module(f"src.app.pages.{name}")
        assert callable(getattr(mod, "render", None)), f"{name} missing render()"


def test_routes_cover_exactly_the_sidebar_pages():
    from src.app.context import PAGES
    from src.app.streamlit_app import ROUTES

    nav = [p for group in PAGES.values() for p in group]
    assert sorted(nav) == sorted(ROUTES), (
        "Sidebar nav and ROUTES diverged - a page is unreachable or a ghost entry remains."
    )
    assert all(callable(fn) for fn in ROUTES.values())
