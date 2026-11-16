"""Guard shared data permissions for adult and child profiles."""
from pathlib import Path
import pytest
from fastapi import HTTPException
from app import main
from app.firestore_store import FirestoreStore, Conflict

ROOT = Path(__file__).resolve().parents[1]

class DummyReq:
    headers = {"x-household-request":"1", "content-type":"application/json", "origin":"https://household.example", "host":"household.example"}

class DummyStore:
    def __init__(self): self.edits=[]; self.actions=[]
    def save_attributes(self, tid, values): self.edits.append((tid,values))
    def change(self, *args): self.actions.append(args); return {"ok":True}

ATTR = main.AttributeUpdate(estimated_minutes=10, physical_effort="Low", mental_effort="Low", age_suitability="All ages", priority="Routine")

@pytest.mark.parametrize("member", ["Ida", "Husband"])
def test_adults_can_edit_attributes(monkeypatch, member):
    db=DummyStore(); monkeypatch.setattr(main, "store", lambda:db); monkeypatch.setattr(main, "writable", lambda:None); monkeypatch.setattr(main, "current_member", lambda request:member)
    assert main.save_attributes("T001", ATTR, DummyReq())["saved"] is True
    assert len(db.edits)==1

def test_daughter_cannot_edit_attributes(monkeypatch):
    db=DummyStore(); monkeypatch.setattr(main, "store", lambda:db); monkeypatch.setattr(main, "writable", lambda:None); monkeypatch.setattr(main, "current_member", lambda request:"Daughter")
    with pytest.raises(HTTPException) as exc: main.save_attributes("T001", ATTR, DummyReq())
    assert exc.value.status_code == 403
    assert not db.edits

def test_daughter_cannot_send_requests(monkeypatch):
    db=DummyStore(); monkeypatch.setattr(main, "store", lambda:db); monkeypatch.setattr(main, "writable", lambda:None); monkeypatch.setattr(main, "current_member", lambda request:"Daughter")
    action = main.ChoreAction(task_id="T001", action="REQUEST", operation_id="123",recipient="Husband")
    with pytest.raises(HTTPException) as exc: main.family_action(action, DummyReq())
    assert exc.value.status_code == 403
    assert not db.actions

def test_daughter_can_decline_incoming_request(monkeypatch):
    db=DummyStore(); monkeypatch.setattr(main, "store", lambda:db); monkeypatch.setattr(main, "writable", lambda:None); monkeypatch.setattr(main, "current_member", lambda request:"Daughter")
    action = main.ChoreAction(task_id="T001", action="DECLINE", operation_id="123",request_id="456")
    assert main.family_action(action, DummyReq()) == {"ok":True}
    assert len(db.actions)==1

def test_store_blocks_daughter_request_even_if_called_directly():
    obj=object.__new__(FirestoreStore)
    with pytest.raises(Conflict, match="cannot send chore requests"):
        obj.change("REQUEST", "Daughter", "T001", "123e4567-e89b-42d3-a456-426614174000", recipient="Husband")

def test_ui_hides_controls_from_daughter():
    js=(ROOT/"static"/"app.js").read_text()
    assert 'member==="Ida" || member==="Husband"' in js
    assert 'if(member!=="Daughter")' in js
