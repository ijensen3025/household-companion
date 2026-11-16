"""Protect against HTML/JavaScript mismatch that makes frequency tabs inert."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def test_index_loads_versioned_javascript_and_styles():
    html = (ROOT / 'static' / 'index.html').read_text()
    assert re.search(r'/static/app\.js\?v=[0-9]+\.[0-9]+\.[0-9]+', html)
    assert re.search(r'/static/styles\.css\?v=[0-9]+\.[0-9]+\.[0-9]+', html)

def test_javascript_tabs_and_api_contract():
    js = (ROOT / 'static' / 'app.js').read_text()
    assert '$("tracker-tabs").addEventListener("click"' in js
    assert 'setView(button.dataset.view)' in js
    assert 'data.ui_contract !== "firestore-v2"' in js
    assert 'c.views?.[activeView]' in js

def test_api_disables_cache_for_dynamic_and_static_files():
    source = (ROOT / 'app' / 'main.py').read_text()
    assert 'resp.headers["Cache-Control"] = "no-store, max-age=0"' in source
    assert '"ui_contract": "firestore-v2"' in (ROOT / "app" / "firestore_store.py").read_text()
