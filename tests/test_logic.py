from datetime import date, timedelta
import pytest
from app.logic import build_chores, summary, suggestions, view_membership, frequency_tab

TODAY=date(2026,11,15)

def one_chore(interval, last, today=TODAY, tid='T058'):
    tasks=[[tid,'Kitchen','Mop floor', '' if interval is None else str(interval),'Routine']]
    history=[[last.isoformat(),tid]] if last else []
    return build_chores(tasks,history,today)[0]

def chosen_tab(chore, today):
    views=view_membership(chore,today)
    assert sum(views.values())==1, f'Should appear in exactly one tab: {views}'
    return next(key for key,value in views.items() if value)

@pytest.mark.parametrize('interval,expected',[
    (1,'daily'),(7,'weekly'),(14,'weekly'),(30,'monthly'),
    (60,'quarterly'),(90,'quarterly'),(180,'yearly'),(365,'yearly'),
    (None,'as_needed'),
])
def test_frequency_categories(interval,expected):
    assert frequency_tab(interval)==expected
    chore=one_chore(interval,TODAY)
    assert chosen_tab(chore,TODAY)==expected

@pytest.mark.parametrize('interval', [1,7,14,30,60,90,180,365])
def test_completed_chore_reappears_on_exact_due_date(interval):
    chore=one_chore(interval,TODAY,TODAY)
    assert chosen_tab(chore,TODAY)=='daily' if interval==1 else chosen_tab(chore,TODAY)!='todo'
    due=TODAY+timedelta(days=interval)
    assert chore['next_suggested']==due.isoformat()
    assert chosen_tab(chore,due-timedelta(days=1))==frequency_tab(interval)
    assert chosen_tab(chore,due)=='todo'
    assert chosen_tab(chore,due+timedelta(days=1))=='todo'


def test_kitchen_mopping_specific_example():
    chore=one_chore(14, date(2026,11,15))
    assert chore['next_suggested']=='2026-11-29'
    assert chosen_tab(chore,date(2026,11,15))=='weekly'
    assert chosen_tab(chore,date(2026,11,28))=='weekly'
    assert chosen_tab(chore,date(2026,11,29))=='todo'
    assert chosen_tab(chore,date(2026,11,30))=='todo'


def test_after_recompletion_recalculates_date_and_tab():
    tasks=[['T058','Kitchen','Mop floor','14','Routine']]
    history=[['2026-11-15','T058'],['2026-11-29','T058']]
    chore=build_chores(tasks,history,date(2026,11,29))[0]
    assert chore['last_completed']=='2026-11-29'
    assert chore['next_suggested']=='2026-12-13'
    assert chosen_tab(chore,date(2026,11,29))=='weekly'
    assert chosen_tab(chore,date(2026,12,13))=='todo'


def test_not_established_is_todo_but_not_overdue():
    chore=one_chore(30,None)
    assert chore['status']=='Not established'
    assert chosen_tab(chore,TODAY)=='todo'
    assert suggestions([chore])==[]


def test_as_needed_has_no_scheduled_return():
    chore=one_chore(None, TODAY)
    assert chore['next_suggested'] is None
    assert chosen_tab(chore,TODAY)=='as_needed'
    assert chosen_tab(chore,TODAY+timedelta(days=365))=='as_needed'
    assert chosen_tab(one_chore(None,None),TODAY)=='todo'


def test_duplicates_do_not_duplicate_tabs():
    tasks=[['T078','Fireplace sitting area','Vacuum sitting area','7','Routine']]
    history=[['2026-11-15','T078'],['2026-11-15','T078']]
    chores=build_chores(tasks,history,TODAY)
    assert chosen_tab(chores[0],TODAY)=='weekly'
    assert summary(chores,history)['completed_today']==1
    assert summary(chores,history)['completions']==2


def test_google_sheet_serial_date():
    chore=build_chores([['T058','Kitchen','Mop floor',14,'Routine']],[[46341,'T058']],TODAY)[0]
    assert chore['last_completed']=='2026-11-15'
    assert chosen_tab(chore,TODAY)=='weekly'


def test_suggestions_exclude_completed():
    tasks=[['T058','Kitchen','Mop floor','14','High'],['T001','Kitchen','Wipe table','7','High']]
    history=[['2026-11-15','T058'],['2026-11-08','T001']]
    chores=build_chores(tasks,history,TODAY)
    assert [x['id'] for x in suggestions(chores)]==['T001']


def test_all_source_frequency_values_are_supported():
    import openpyxl
    from pathlib import Path
    workbook=Path('/mnt/data/files/household_chore_tracker.xlsx')
    if not workbook.exists():
        pytest.skip('Source workbook only available in development environment')
    ws=openpyxl.load_workbook(workbook,read_only=True,data_only=True)['Chore Tracker']
    rows=[r for r in list(ws.values)[1:] if isinstance(r[0],str) and r[0].startswith('T')]
    assert len(rows)==129
    for r in rows:
        chore=build_chores([r[:5]],[[TODAY.isoformat(),r[0]]],TODAY)[0]
        assert chosen_tab(chore,TODAY)==frequency_tab(chore['frequency_days'])
