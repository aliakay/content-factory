import pytest


@pytest.fixture(autouse=True)
def _review_on(monkeypatch):
    """Tests assume the reviewer runs, whatever the local config.env says (CF_HAT_REVIEW=0 switches it off)."""
    monkeypatch.setenv("CF_HAT_REVIEW", "1")
