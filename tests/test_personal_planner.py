"""The planner belongs to the authenticated household member, not a preview selection."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_no_profile_preview_selector():
    html = (ROOT / "static/index.html").read_text()
    js = (ROOT / "static/app.js").read_text()
    assert "Planning preview for" not in html
    assert 'id="planner-preview"' not in html
    assert "planner-preview" not in js
    assert "preview_for" not in js

def test_backend_uses_authenticated_actor_for_recommendations():
    source = (ROOT / "app/firestore_store.py").read_text()
    assert "member=actor, assignments=assigned" in source
    assert '"planner": actor' in source
    assert 'planner = preview' not in source
    api = (ROOT / "app/main.py").read_text()
    assert "preview_for" not in api
