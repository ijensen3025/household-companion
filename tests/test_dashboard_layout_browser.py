"""Real Chromium interactions with mocked API; never connects to Firestore."""
import shutil
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ['family', 'planner', 'management', 'tracker']
KEY = 'household-companion:dashboard-layout:v1:'

@pytest.fixture
def dashboard():
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    chromium = shutil.which("chromium") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Install Chromium to run dashboard browser tests")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium, args=['--no-sandbox'])
        page = browser.new_page(viewport={"width": 1280, "height": 2000})
        actor = {'name': 'Ida'}
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def respond(route):
            path = route.request.url.split('household.test', 1)[1].split('?')[0]
            if path == '/api/chores':
                route.fulfill(json={'ui_contract': 'firestore-v2', 'member': actor['name'],
                    'family_enabled': True, 'family_configured': True, 'chores': [],
                    'summary': {'total': 0, 'areas': 1, 'completions': 0},
                    'suggestions': [], 'assigned': {}, 'requests': [], 'areas': ['Kitchen']})
            else:
                file = ROOT / ('static/index.html' if path == '/' else path.lstrip('/'))
                route.fulfill(path=str(file))
        page.route('https://household.test/**', respond)
        page.goto('https://household.test/')
        page.wait_for_function('document.getElementById("dashboard-layout-tools").hidden === false')
        yield page, actor
        assert not errors
        browser.close()

def order(page):
    return page.locator('#dashboard-cards > section').evaluate_all('(cards) => cards.map(c => c.dataset.dashboardCard)')

def test_drag_save_reload_and_preserve_controls(dashboard):
    page, _ = dashboard
    page.locator('#search').fill('windows')
    page.locator('[data-frequency="monthly"]').click()
    page.locator('#area-create-form input').fill('Porch')
    page.locator('[data-dashboard-card="planner"] .layout-drag').drag_to(
        page.locator('[data-dashboard-card="family"] .layout-drag'))
    assert order(page) == ['planner', 'family', 'management', 'tracker']
    assert page.locator('#search').input_value() == 'windows'
    assert page.locator('#area-create-form input').input_value() == 'Porch'
    assert page.locator('#tab-heading').inner_text() == 'Monthly chores'
    page.locator('[data-energy="low"]').click()
    page.wait_for_function('document.querySelector("#updated").textContent.startsWith("Updated")')
    assert order(page)[0] == 'planner'
    page.reload()
    page.wait_for_selector('#dashboard-layout-tools')
    assert order(page)[0] == 'planner'
    page.locator('#reset-dashboard-layout').click()
    assert order(page) == DEFAULT

def test_member_isolation_hidden_card_and_keyboard(dashboard):
    page, actor = dashboard
    up = page.locator('[data-dashboard-card="tracker"] [data-layout-up]')
    up.focus()
    page.keyboard.press('Enter')
    assert order(page) == ['family', 'planner', 'tracker', 'management']
    actor['name'] = 'Daughter'
    page.evaluate('load()')
    assert order(page) == DEFAULT
    assert not page.locator('#chore-management').is_visible()
    assert page.locator('[data-dashboard-card="tracker"] [data-layout-down]').is_disabled()
    page.locator('[data-dashboard-card="tracker"] [data-layout-up]').click()
    assert order(page) == ['family', 'tracker', 'planner', 'management']
    assert not page.locator('#chore-management').is_visible()
    actor['name'] = 'Ida'
    page.evaluate('load()')
    assert order(page) == ['family', 'planner', 'tracker', 'management']
    assert page.locator('#chore-management').is_visible()

def test_bad_preferences_and_unavailable_storage(dashboard):
    page, _ = dashboard
    page.evaluate('(key) => localStorage.setItem(key, JSON.stringify(["unknown", "tracker", "tracker"]))', KEY + 'Ida')
    page.reload()
    page.wait_for_selector('#dashboard-layout-tools')
    assert order(page) == ['tracker', 'family', 'planner', 'management']
    page.evaluate('() => { Storage.prototype.setItem = () => { throw new Error("blocked"); }; }')
    page.locator('[data-dashboard-card="tracker"] [data-layout-down]').click()
    assert 'could not save' in page.locator('#dashboard-layout-status').inner_text()
    page.evaluate('(key) => localStorage.removeItem(key)', KEY + 'Ida')
    page.reload()
    page.wait_for_selector('#dashboard-layout-tools')
    assert order(page) == DEFAULT
