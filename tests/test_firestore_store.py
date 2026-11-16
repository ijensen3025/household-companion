from datetime import date
from copy import deepcopy
from uuid import uuid4
import pytest
from app.firestore_store import FirestoreStore, working_state, chore_available, Conflict


class Snapshot:
    def __init__(self, value):
        self.value = deepcopy(value)
        self.exists = value is not None
    def to_dict(self):
        return deepcopy(self.value)

class Doc:
    def __init__(self, db, collection, key):
        self.db, self.collection, self.key = db, collection, key
    @property
    def id(self): return self.key
    def get(self, transaction=None):
        return Snapshot(self.db.docs.get(self.collection, {}).get(self.key))
    def update(self, data):
        self.db.update(self, data)
    def create(self, data):
        assert self.key not in self.db.docs.get(self.collection, {})
        self.db.docs.setdefault(self.collection,{})[self.key] = deepcopy(data)

class Collection:
    def __init__(self, db, name): self.db, self.name = db, name
    def document(self, key): return Doc(self.db, self.name, key)
    def where(self, field, op, value):
        class Filtered:
            def stream(inner):
                for doc in self.stream():
                    if doc.to_dict().get(field) == value: yield doc
        return Filtered()
    def stream(self):
        for key, value in self.db.docs.get(self.name, {}).items():
            obj = Snapshot(value);obj.id = key
            yield obj

class Transaction:
    def __init__(self, db): self.db=db;self.writes=[]
    def update(self, ref, data): self.writes.append(("update", ref, data))
    def create(self, ref, data): self.writes.append(("create", ref, data))
    def delete(self, ref): self.writes.append(("delete", ref, None))
    def commit(self):
        for op, ref, data in self.writes:
            if op == "create":
                assert ref.key not in self.db.docs.get(ref.collection, {})
                self.db.docs.setdefault(ref.collection,{})[ref.key] = deepcopy(data)
            elif op == "delete": self.db.docs[ref.collection].pop(ref.key)
            else: self.db.update(ref,data)

class DB:
    def __init__(self):
        self.docs = {"chores": {"T058": {
            "task_id": "T058", "name": "Mop floor", "area": "Kitchen",
            "frequency_days": 14, "priority": "Routine", "last_completed_on": "2026-11-01",
            "attributes": {"estimated_minutes": 15, "physical_effort": "Medium",
                "mental_effort": "Low", "age_suitability": "Adults only"},
        }}, "completions": {}, "chore_requests": {}, "operations": {}}
    def collection(self, name): return Collection(self,name)
    def transaction(self): return Transaction(self)
    def update(self, ref, data):
        target = self.docs[ref.collection][ref.key]
        for key,value in data.items():
            if "." in key:
                outer,inner = key.split(".",1)
                target.setdefault(outer,{})[inner] = deepcopy(value)
            else: target[key] = deepcopy(value)

# Firestore's decorator commits the transaction after the wrapped function exits.
@pytest.fixture(autouse=True)
def fake_transaction(monkeypatch):
    import app.firestore_store as m
    def wrap(f):
        def inner(txn):
            result=f(txn)
            txn.commit()
            return result
        return inner
    monkeypatch.setattr(m.firestore, "transactional", wrap)
    monkeypatch.setattr(m, "today_local", lambda:date(2026,11,15))


def action(store, name, actor="Ida", task="T058", **kwargs):
    return store.change(name,actor,task,str(uuid4()),**kwargs)


def test_due_date_returns_on_exact_day():
    c = {"last_completed_on":"2026-11-15", "frequency_days":14}
    assert not chore_available(c,date(2026,11,28))
    assert chore_available(c,date(2026,11,29))
    assert chore_available(c,date(2026,12,1))


def test_claim_exclusive_and_release():
    db=DB();store=FirestoreStore(db)
    action(store,"CLAIM")
    assert db.docs["chores"]["T058"]["active_assignment"] == "Ida"
    with pytest.raises(Conflict,match="already assigned"):
        action(store,"CLAIM",actor="Husband")
    action(store,"RELEASE")
    action(store,"CLAIM",actor="Husband")
    assert db.docs["chores"]["T058"]["active_assignment"] == "Husband"


def test_pending_request_only_assigns_on_accept():
    db=DB();store=FirestoreStore(db)
    req=action(store,"REQUEST",recipient="Husband")
    assert db.docs["chores"]["T058"].get("active_assignment") is None
    assert len(db.docs["chore_requests"]) == 1
    with pytest.raises(Conflict,match="addressed"):
        action(store,"ACCEPT",request_id=req["request_id"])
    action(store,"ACCEPT",actor="Husband",request_id=req["request_id"])
    assert db.docs["chores"]["T058"]["active_assignment"] == "Husband"
    assert db.docs["chore_requests"][req["request_id"]]["status"] == "accepted"


def test_claim_closes_other_pending_requests():
    db=DB();store=FirestoreStore(db)
    req=action(store,"REQUEST",recipient="Husband")
    action(store,"CLAIM")
    assert db.docs["chore_requests"][req["request_id"]]["status"] == "closed"
    assert not db.docs["chores"]["T058"]["pending_request_ids"]


def test_decline_returns_to_pool():
    db=DB();store=FirestoreStore(db)
    req=action(store,"REQUEST",recipient="Husband")
    action(store,"DECLINE",actor="Husband",request_id=req["request_id"])
    assert db.docs["chore_requests"][req["request_id"]]["status"] == "declined"
    action(store,"CLAIM")


def test_completion_is_atomic_and_idempotent():
    db=DB();store=FirestoreStore(db)
    action(store,"CLAIM")
    opid=str(uuid4())
    result=store.change("COMPLETE","Ida","T058",opid)
    assert result["date"] == "2026-11-15"
    assert store.change("COMPLETE","Ida","T058",opid) == result
    assert len(db.docs["completions"]) == 1
    assert db.docs["chores"]["T058"]["last_completed_on"] == "2026-11-15"
    assert db.docs["chores"]["T058"]["active_assignment"] is None
    with pytest.raises(Conflict,match="not currently available"):
        action(store,"COMPLETE")


def test_imported_data_powers_existing_tabs():
    db=DB()
    db.docs["completions"]["sheet_row_000002"]={"task_id":"T058", "completed_on":"2026-11-01"}
    chores,hist,assigned,reqs=working_state(db.docs["chores"],db.docs["completions"],{},date(2026,11,15))
    assert chores[0]["views"]["todo"] is True
    assert chores[0]["next_suggested"] == "2026-11-15"
    assert hist and not assigned and not reqs


def test_attribute_update_preserves_chore_identity():
    db=DB();store=FirestoreStore(db)
    store.save_attributes("T058",{"estimated_minutes":20,"physical_effort":"Low","mental_effort":"Low",
        "age_suitability":"All ages", "priority":"High"})
    doc=db.docs["chores"]["T058"]
    assert doc["name"] == "Mop floor" and doc["attributes"]["estimated_minutes"] == 20
    assert doc["priority"] == "High"


def test_daughter_cannot_claim_adult_only_chore():
    db=DB();store=FirestoreStore(db)
    with pytest.raises(Conflict,match="suitable"):
        action(store,"CLAIM",actor="Daughter")
