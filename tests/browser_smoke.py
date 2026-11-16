"""Optional local Chromium smoke test. Mocks API; no live sheet access."""
import json
import re
import subprocess
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
API = {
 'ui_contract':'firestore-v2', 'as_of':'2026-11-15',
 'summary':{'total':2,'areas':1,'completions':1},
 'family_enabled':True,'family_configured':True,'member':'Ida','planner':'Ida',
 'assigned':{'T001':'Husband'}, 'requests':[],
 'suggestions':[],
 'chores':[
   {'id':'T001','name':'Clean sink','area':'Kitchen','priority':'High','status':'Suggested today',
    'next_suggested':'2026-11-15','last_completed':'2026-11-08','assigned_to':'Husband','pending_for':[],
    'attributes':{'estimated_minutes':5,'physical_effort':'Low','mental_effort':'Low','age_suitability':'All ages'},
    'frequency_days':7,'views':{'todo':True,'daily':False,'weekly':False,'monthly':False,'quarterly':False,'yearly':False,'as_needed':False}},
   {'id':'T002','name':'Mop floor','area':'Kitchen','priority':'Routine','status':'Upcoming',
    'next_suggested':'2026-11-29','last_completed':'2026-11-15','assigned_to':None,'pending_for':[],
    'attributes':{'estimated_minutes':15,'physical_effort':'Medium','mental_effort':'Low','age_suitability':'Adults only'},
    'frequency_days':14,'views':{'todo':False,'daily':False,'weekly':True,'monthly':False,'quarterly':False,'yearly':False,'as_needed':False}}
 ]
}
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=browser.new_page()
  html=(ROOT/'static/index.html').read_text()
  html=re.sub(r'<link rel="stylesheet" href="/static/([^?]+)\?v=[^"]+">',
              lambda match: '<style>'+(ROOT/'static'/match[1]).read_text()+'</style>', html)
  html=re.sub(r'<script src="/static/[^" ]+" defer></script>', '', html)
  fake="<script>window.fetch = async function(url) { if(String(url).includes('/api/chores?')) return {ok:true,json:async()=>API_DATA}; return {ok:false,json:async()=>({detail:'not mocked'})}; }; const API_DATA = __DATA__;</script>"
  html=html.replace('</head>', fake.replace('__DATA__',json.dumps(API))+'</head>')
  html=html.replace('</body>', '<script>'+(ROOT/'static/dashboard-layout.js').read_text()+'</script><script>'+(ROOT/'static/app.js').read_text()+'</script></body>')
  page.set_content(html)
  page.wait_for_timeout(400)
  assert page.locator('#tab-heading').inner_text()=='Daily chores'
  assert page.locator('#chore-list').get_by_text('Clean sink').count()==0, 'assigned chore is not To Do'
  page.locator('button[data-frequency=biweekly]').click()
  page.locator('button[data-tracker-status=completed]').click()
  assert page.locator('#tab-heading').inner_text()=='Biweekly chores'
  assert page.locator('#chore-list').get_by_text('Mop floor').count()==1
  assert page.locator('#family-summary').count()==1
  browser.close()
 print('Chromium smoke test passed: tab switching, completed list, assigned exclusion')
finally:
 pass
