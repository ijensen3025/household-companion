"""Firestore transaction and HTTP permission tests for v2.4 functionality."""
from datetime import date
from uuid import uuid4
from copy import deepcopy
import pytest
from fastapi import HTTPException
from app import main
from app.firestore_store import FirestoreStore, Conflict, working_state
from test_firestore_store import DB

class Request:
    headers={"x-household-request":"1", "content-type":"application/json",
             "origin":"https://household.example", "host":"household.example"}

@pytest.fixture(autouse=True)
def txn(monkeypatch):
    import app.firestore_store as store
    def deco(func):
        def wrapper(txn):
            result=func(txn)
            txn.commit()
            return result
        return wrapper
    monkeypatch.setattr(store.firestore,"transactional",deco)
    monkeypatch.setattr(store,"today_local",lambda: date(2026,11,15))


def test_create_new_area_and_chore_with_incrementing_ids():
    db=DB();s=FirestoreStore(db)
    assert s.create_area("Ida","Front Porch")["area"] == "Front Porch"
    with pytest.raises(Conflict,match="already exists"):
        s.create_area("Husband","front porch")
    values={"name":"Sweep steps", "area":"Front Porch", "frequency_days":7,
            "estimated_minutes":10, "physical_effort":"Low", "mental_effort":"Low", "age_suitability":"All ages"}
    first=s.create_chore("Husband",values)
    assert first["task_id"] == "T059"
    second=s.create_chore("Ida",{**values,"name":"Wipe door", "frequency_days":None})
    assert second["task_id"] == "T060"
    assert db.docs["chores"]["T059"]["last_completed_on"] is None
    assert db.docs["chores"]["T060"]["frequency_days"] is None
    assert db.docs["household_metadata"]["chore_counter"]["last_id"] == 60
    chores,history,_,_=working_state(db.docs["chores"],db.docs["completions"],{},date(2026,11,15))
    assert next(c for c in chores if c["id"]=="T059")["views"]["todo"]


def test_parent_only_create_area_chore_backend():
    db=DB();s=FirestoreStore(db)
    with pytest.raises(Conflict,match="parents"):
        s.create_area("Daughter","Front porch")
    with pytest.raises(Conflict,match="parents"):
        s.create_chore("Daughter",{})
    for actor in ("Daughter",):
        from unittest.mock import Mock
        old=main.current_member
        main.current_member=lambda request: actor
        main.store=lambda: s
        main.writable=lambda: None
        try:
            with pytest.raises(HTTPException) as e:
                main.create_area(main.AreaCreate(name="Porch"),Request())
            assert e.value.status_code == 403
            with pytest.raises(HTTPException) as e:
                main.create_chore(main.ChoreCreate(name="Sweep",area="Kitchen",frequency_days=7,
                  estimated_minutes=10,physical_effort="Low",mental_effort="Low",age_suitability="All ages"),Request())
            assert e.value.status_code == 403
        finally:
            main.current_member=old


def test_undo_first_completion_returns_to_todo():
    db=DB();s=FirestoreStore(db)
    db.docs["chores"]["T058"]["last_completed_on"] = None
    opid=str(uuid4())
    s.change("COMPLETE","Ida","T058",opid)
    assert s.undoable_completions(db.docs["chores"], db.docs["completions"],"Ida")["T058"]["completion_id"]==opid
    result=s.undo_completion("Husband","T058",str(uuid4()),opid)
    assert result["last_completed_on"] is None
    assert db.docs["completions"]=={}
    assert len(db.docs["completion_undos"])==1
    chores,_,_,_=working_state(db.docs["chores"],db.docs["completions"],{},date(2026,11,15))
    assert chores[0]["views"]["todo"]
    assert chores[0]["last_completed"] is None


def test_undo_restores_previous_date_and_completed_tab():
    db=DB();s=FirestoreStore(db)
    db.docs["completions"]["old"]={"task_id":"T058","completed_on":"2026-11-01"}
    id=str(uuid4());s.change("COMPLETE","Ida","T058",id)
    undo_id=str(uuid4());result=s.undo_completion("Ida","T058",undo_id,id)
    assert result["last_completed_on"]=="2026-11-01"
    assert s.undo_completion("Ida","T058",undo_id,id)==result
    assert set(db.docs["completions"])=={"old"}
    chores,_,_,_=working_state(db.docs["chores"],db.docs["completions"],{},date(2026,11,14))
    assert chores[0]["views"]["weekly"]
    assert chores[0]["next_suggested"]=="2026-11-15"
    chores,_,_,_=working_state(db.docs["chores"],db.docs["completions"],{},date(2026,11,15))
    assert chores[0]["views"]["todo"]


def test_daughter_may_only_undo_own_record():
    db=DB();s=FirestoreStore(db)
    db.docs["chores"]["T058"]["attributes"]["age_suitability"]="All ages"
    op=str(uuid4());s.change("COMPLETE","Daughter","T058",op)
    assert s.undoable_completions(db.docs["chores"],db.docs["completions"],"Daughter")["T058"]["completed_by"]=="Daughter"
    s.undo_completion("Daughter","T058",str(uuid4()),op)
    db.docs["chores"]["T058"]["last_completed_on"]="2026-11-01"
    db.docs["chores"]["T058"]["last_completion_id"]=None
    db.docs["completions"]["imported"]={"task_id":"T058","completed_on":"2026-11-01"}
    assert "T058" not in s.undoable_completions(db.docs["chores"],db.docs["completions"],"Daughter")
    with pytest.raises(Conflict, match="own"):
        s.undo_completion("Daughter","T058",str(uuid4()),"imported")
    s.undo_completion("Husband","T058",str(uuid4()),"imported")


def test_stale_undo_and_unknown_area_rejected():
    db=DB();s=FirestoreStore(db)
    db.docs["completions"]["one"]={"task_id":"T058","completed_on":"2026-11-01"}
    db.docs["completions"]["two"]={"task_id":"T058","completed_on":"2026-11-15","completed_by":"Ida"}
    db.docs["chores"]["T058"]["last_completed_on"]="2026-11-15"
    with pytest.raises(Conflict,match="latest"):
        s.undo_completion("Ida","T058",str(uuid4()),"one")
    with pytest.raises(ValueError, match="Create the household area"):
        s.create_chore("Ida", {"name":"Sweep", "area":"Unknown", "frequency_days":1,
          "estimated_minutes":10,"physical_effort":"Low","mental_effort":"Low","age_suitability":"All ages"})

def test_new_chore_does_not_trigger_old_129_limit():
    db=DB();s=FirestoreStore(db)
    original=deepcopy(db.docs["chores"]["T058"])
    for number in range(1,130):
        if number != 58:
            db.docs["chores"][f"T{number:03d}"]={**deepcopy(original),"task_id":f"T{number:03d}"}
    s.create_chore("Ida",{"name":"Clean pantry shelves","area":"Kitchen","frequency_days":30,
                "estimated_minutes":20,"physical_effort":"Medium","mental_effort":"Medium",
                "age_suitability":"Adults only"})
    assert len(db.docs["chores"])==130
    assert "T130" in db.docs["chores"]
    data=s.dashboard("Ida")
    assert data["summary"]["total"] == 130
    assert data["chores"][-1]["id"] == "T130"


def test_empty_new_area_visible_as_choice_and_in_count():
    db=DB();s=FirestoreStore(db)
    s.create_area("Husband","Utility closet")
    state=s.dashboard("Husband")
    assert "Utility closet" in state["areas"]
    assert state["summary"]["areas"] == 2


def test_ui_admin_and_undo_controls_exist():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    script=(root/"static"/"app.js").read_text()
    markup=(root/"static"/"index.html").read_text()
    assert '$("chore-management").hidden=!parent' in script
    assert 'if(undoable[c.id]) actions.append(undoButton(c))' in script
    assert 'id="area-create-form"' in markup
    assert 'id="chore-create-form"' in markup
