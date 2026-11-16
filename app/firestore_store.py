"""Firestore primary data layer; no Google Sheets calls during app operation.

Initial documents are produced by household-firestore-migration/migrate.py.
Each task document is the serialization point for assignment, request, and
completion transitions. Document writes are performed in a Firestore transaction.
"""
import os
from datetime import datetime, date, timezone
from uuid import UUID, uuid4
import re
import unicodedata
from zoneinfo import ZoneInfo

from google.cloud import firestore
from .logic import build_chores, summary, view_membership
from .attributes import recommend, EFFORT, AGE, PRIORITIES
from .family import MEMBERS, age_allowed

PROJECT = "household-chore-tracker-514819"
DATABASE = "household-tracker"  # Named database, not (default).
TZ = ZoneInfo("America/Chicago")


class Conflict(ValueError):
    """Business-rule conflict, represented as HTTP 409."""


def today_local():
    return datetime.now(TZ).date()


def validate_operation_id(value):
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("operation_id must be a UUID")


def chore_available(doc, today):
    """Available iff never completed or due on/before today; not if completed today."""
    last = doc.get("last_completed_on")
    if not last:
        return True
    if last == today.isoformat():
        return False
    interval = doc.get("frequency_days")
    if interval is None:
        return False
    from datetime import timedelta
    return date.fromisoformat(last) + timedelta(days=int(interval)) <= today


def working_state(chore_docs, completion_docs, request_docs, today):
    """Adapt imported Firestore schema to the original dashboard contract."""
    tasks = [[c["task_id"], c["area"], c["name"],
              c.get("frequency_days") or "", c["priority"]]
             for c in sorted(chore_docs.values(), key=lambda x: x["task_id"])]
    history = [[c["completed_on"], c["task_id"], c.get("area_at_completion", ""),
                c.get("chore_at_completion", ""), c.get("notes", "")]
               for c in completion_docs.values()]
    chores = build_chores(tasks, history, today=today)
    assigned = {}
    requests = []
    for c in chores:
        doc = chore_docs[c["id"]]
        c["views"] = view_membership(c, today)
        attrs = dict(doc["attributes"])
        attrs["priority"] = doc["priority"]
        c["attributes"] = attrs
        assignee = doc.get("active_assignment")
        # stale assignments from a prior cycle should not block newly due chores
        if assignee and c["views"]["todo"]:
            assigned[c["id"]] = assignee
        c["assigned_to"] = assigned.get(c["id"])
        c["pending_for"] = []
    for rid, r in request_docs.items():
        item = {"id": rid, "task_id": r["task_id"], "from": r["from"],
                "to": r["to"], "note": r.get("note", ""), "status": r["status"]}
        requests.append(item)
        if r["status"] == "pending" and r["task_id"] in chore_docs:
            match = next((c for c in chores if c["id"] == r["task_id"]), None)
            if match and match["views"]["todo"] and not match["assigned_to"]:
                match["pending_for"].append(r["to"])
    return chores, history, assigned, requests


def clean_label(value, maximum):
    text = " ".join(str(value or "").split())
    if not text or len(text) > maximum or any(ord(ch) < 32 for ch in text):
        raise ValueError(f"Name must contain 1–{maximum} printable characters")
    return text


def normalize_area_key(text):
    # Readable document ID, one per case-insensitive household area.
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "-".join(normalized.split())


class FirestoreStore:
    def __init__(self, client=None):
        self.db = client or firestore.Client(
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", PROJECT),
            database=os.environ.get("FIRESTORE_DATABASE", DATABASE))

    def _load_raw(self):
        chores = {d.id: d.to_dict() for d in self.db.collection("chores").stream()}
        if not chores:
            raise ValueError("Firestore has no chores; the migration may be incomplete")
        if not all(re.fullmatch(r"T\d{3,}", tid) and doc.get("task_id") == tid for tid, doc in chores.items()):
            raise ValueError("Invalid chore identities in Firestore")
        completions = {d.id: d.to_dict() for d in self.db.collection("completions").stream()}
        requests = {d.id: d.to_dict() for d in self.db.collection("chore_requests").stream()}
        return chores, completions, requests

    def _areas(self, chores):
        registered = [d.to_dict().get("name", "") for d in self.db.collection("household_areas").stream()]
        return sorted({*registered, *(c["area"] for c in chores.values())} - {""}, key=str.casefold)

    def dashboard(self, actor, energy="medium", minutes=20, mode="maintain", room=""):
        chores_raw, history_raw, requests_raw = self._load_raw()
        today = today_local()
        chores, history, assigned, requests = working_state(chores_raw, history_raw, requests_raw, today)
        areas = self._areas(chores_raw)
        overview = summary(chores, history)
        overview["areas"] = len(areas)
        return {
            "chores": chores, "summary": overview,
            "suggestions": recommend(chores, energy=energy, minutes=minutes,
                 mode=mode, room=room, member=actor, assignments=assigned, today=today),
            "family_enabled": True, "family_configured": True,
            "member": actor, "planner": actor,
            "assigned": assigned, "requests": requests,
            "areas": areas,
            "undoable": self.undoable_completions(chores_raw, history_raw, actor),
            "as_of": today.isoformat(), "ui_contract": "firestore-v2",
            "backend": "firestore",
        }

    @staticmethod
    def _completion_order(item):
        # Legacy imported completions have no created_at or completed_by.
        key, doc = item
        return (doc.get("completed_on", ""), str(doc.get("created_at") or ""), key)

    def undoable_completions(self, chores, completions, actor):
        result = {}
        for task_id, chore in chores.items():
            records = sorted(((cid, c) for cid, c in completions.items()
                              if c.get("task_id") == task_id), key=self._completion_order)
            if not records:
                continue
            cid, latest = records[-1]
            if latest.get("completed_on") != chore.get("last_completed_on"):
                continue
            if chore.get("last_completion_id") and chore["last_completion_id"] != cid:
                continue
            if actor in ("Ida", "Husband") or latest.get("completed_by") == actor:
                result[task_id] = {"completion_id": cid, "completed_on": latest["completed_on"],
                                   "completed_by": latest.get("completed_by") or "Unknown (imported)"}
        return result

    def undo_completion(self, actor, task_id, operation_id, completion_id):
        """Remove latest completion only; keep an audit record, recalculate prior date.

        Reads all candidate history before the transaction and verifies the chore's
        completion pointer within the transaction. Concurrent new completions update
        the same chore, so Firestore retries and rejects stale undo attempts.
        """
        validate_operation_id(operation_id)
        if actor not in MEMBERS:
            raise Conflict("Unknown household member")
        if not completion_id or len(completion_id) > 180 or "/" in completion_id:
            raise Conflict("Invalid completion ID")
        op_ref = self.db.collection("operations").document(operation_id)
        previous_attempt = op_ref.get()
        if previous_attempt.exists:
            saved = previous_attempt.to_dict()
            if (saved.get("action"), saved.get("actor"), saved.get("task_id"), saved.get("completion_id")) != ("UNDO_COMPLETE", actor, task_id, completion_id):
                raise Conflict("Operation ID already used for a different action")
            return saved["result"]
        records = [(d.id, d.to_dict()) for d in self.db.collection("completions")
                   .where("task_id", "==", task_id).stream()]
        records.sort(key=self._completion_order)
        if not records or records[-1][0] != completion_id:
            raise Conflict("That is no longer the latest completion; refresh the page")
        _, target = records[-1]
        if actor == "Daughter" and target.get("completed_by") != actor:
            raise Conflict("You can only undo your own completions")
        previous_id, previous = records[-2] if len(records) > 1 else (None, None)
        latest_date = target.get("completed_on")
        now = datetime.now(timezone.utc).isoformat()
        task_ref = self.db.collection("chores").document(task_id)
        target_ref = self.db.collection("completions").document(completion_id)
        previous_ref = self.db.collection("completions").document(previous_id) if previous_id else None
        op_ref = self.db.collection("operations").document(operation_id)
        audit_ref = self.db.collection("completion_undos").document(operation_id)

        @firestore.transactional
        def commit(txn):
            op = op_ref.get(transaction=txn)
            if op.exists:
                saved = op.to_dict()
                if (saved.get("action"), saved.get("actor"), saved.get("task_id"), saved.get("completion_id")) != ("UNDO_COMPLETE", actor, task_id, completion_id):
                    raise Conflict("Operation ID already used for a different action")
                return saved["result"]
            snap = task_ref.get(transaction=txn)
            latest_snap = target_ref.get(transaction=txn)
            prior_snap = previous_ref.get(transaction=txn) if previous_ref else None
            if not snap.exists or not latest_snap.exists:
                raise Conflict("Chore or completion no longer exists")
            chore = snap.to_dict()
            latest = latest_snap.to_dict()
            if (chore.get("last_completed_on") != latest_date or
                (chore.get("last_completion_id") and chore["last_completion_id"] != completion_id) or
                latest != target):
                raise Conflict("Completion history changed; refresh before undoing")
            if chore.get("active_assignment") or chore.get("pending_request_ids"):
                raise Conflict("Release assignments and resolve pending requests before undoing")
            if previous_ref and (not prior_snap.exists or prior_snap.to_dict() != previous):
                raise Conflict("Earlier completion history changed")
            if actor == "Daughter" and latest.get("completed_by") != "Daughter":
                raise Conflict("You can only undo your own completions")
            txn.update(task_ref, {"last_completed_on": previous.get("completed_on") if previous else None,
                                  "last_completion_id": previous_id, "activity_updated_at": now})
            txn.delete(target_ref)
            txn.create(audit_ref, {"task_id": task_id, "completion_id": completion_id,
                 "completion": latest, "undone_by": actor, "undone_at": now})
            result = {"saved": True, "task_id": task_id, "action": "UNDO_COMPLETE",
                      "last_completed_on": previous.get("completed_on") if previous else None}
            txn.create(op_ref, {"actor": actor, "action": "UNDO_COMPLETE", "task_id": task_id,
                       "completion_id": completion_id, "result": result, "created_at": now})
            return result
        return commit(self.db.transaction())

    def create_area(self, actor, name):
        if actor not in ("Ida", "Husband"):
            raise Conflict("Only parents can create household areas")
        name = clean_label(name, 70)
        key = normalize_area_key(name)
        existing = self._areas({})
        if any(normalize_area_key(a) == key for a in existing):
            raise Conflict("That household area already exists")
        # Also guard against historical areas that have no registry document.
        chores = {d.id: d.to_dict() for d in self.db.collection("chores").stream()}
        if any(normalize_area_key(c["area"]) == key for c in chores.values()):
            raise Conflict("That household area already exists")
        try:
            self.db.collection("household_areas").document(key).create({
                "name": name, "created_by": actor,
                "created_at": datetime.now(timezone.utc).isoformat()})
        except Exception as exc:
            # Never overwrite an existing area.
            from google.api_core.exceptions import AlreadyExists
            if isinstance(exc, AlreadyExists):
                raise Conflict("That household area already exists")
            raise
        return {"saved": True, "area": name}

    def create_chore(self, actor, values):
        if actor not in ("Ida", "Husband"):
            raise Conflict("Only parents can add chores")
        name = clean_label(values["name"], 100)
        area = clean_label(values["area"], 70)
        frequency = values.get("frequency_days")
        if frequency is not None and (type(frequency) is not int or frequency < 1 or frequency > 3650):
            raise ValueError("Frequency must be between 1 and 3650 days, or as needed")
        attrs = {k: values[k] for k in ("estimated_minutes", "physical_effort", "mental_effort", "age_suitability")}
        if type(attrs["estimated_minutes"]) is not int or not 1 <= attrs["estimated_minutes"] <= 240 or any(
            attrs[k] not in EFFORT for k in ("physical_effort", "mental_effort")) or attrs["age_suitability"] not in AGE:
            raise ValueError("Invalid chore attributes")
        existing = {d.id: d.to_dict() for d in self.db.collection("chores").stream()}
        areas = self._areas(existing)
        matches = [a for a in areas if normalize_area_key(a) == normalize_area_key(area)]
        if not matches:
            raise ValueError("Create the household area before adding a chore to it")
        area = matches[0]
        max_id = max((int(i[1:]) for i in existing if re.fullmatch(r"T\d{3,}", i)), default=0)
        counter_ref = self.db.collection("household_metadata").document("chore_counter")
        now = datetime.now(timezone.utc).isoformat()

        @firestore.transactional
        def commit(txn):
            counter = counter_ref.get(transaction=txn)
            current = counter.to_dict().get("last_id", 0) if counter.exists else 0
            number = max(max_id, int(current)) + 1
            task_id = f"T{number:03d}"
            chore_ref = self.db.collection("chores").document(task_id)
            if chore_ref.get(transaction=txn).exists:
                raise Conflict("Task ID collision; retry the request")
            data = {"task_id": task_id, "name": name, "area": area,
                    "frequency_days": frequency, "priority": "Routine", "attributes": attrs,
                    "last_completed_on": None, "last_completion_id": None,
                    "active_assignment": None, "pending_request_ids": [],
                    "created_by": actor, "created_at": now, "activity_updated_at": now}
            txn.create(chore_ref, data)
            if counter.exists:
                txn.update(counter_ref, {"last_id": number})
            else:
                txn.create(counter_ref, {"last_id": number})
            return {"saved": True, "task_id": task_id, "area": area, "name": name}
        return commit(self.db.transaction())

    def save_attributes(self, task_id, values):
        ref = self.db.collection("chores").document(task_id)
        if not ref.get().exists:
            raise ValueError("Unknown chore")
        if values["physical_effort"] not in EFFORT or values["mental_effort"] not in EFFORT or values["age_suitability"] not in AGE or values["priority"] not in PRIORITIES:
            raise ValueError("Invalid attribute value")
        ref.update({"attributes.estimated_minutes": values["estimated_minutes"],
                    "attributes.physical_effort": values["physical_effort"],
                    "attributes.mental_effort": values["mental_effort"],
                    "attributes.age_suitability": values["age_suitability"],
                    "priority": values["priority"]})

    def change(self, action, actor, task_id, operation_id, recipient="", request_id="", note=""):
        """One atomic, idempotent chore action; all conflict checks are in transaction.

        Every action updates the task doc, forcing concurrent claims/requests/
        completions to contend for the same document. Pending requests are
        tracked by ID on the task and atomically closed when it is claimed/done.
        """
        validate_operation_id(operation_id)
        if actor not in MEMBERS:
            raise Conflict("Unknown household member")
        if actor == "Daughter" and action == "REQUEST":
            raise Conflict("Child household members cannot send chore requests")
        if action not in ("REQUEST", "ACCEPT", "DECLINE", "CLAIM", "RELEASE", "COMPLETE"):
            raise ValueError("Unsupported family action")
        db = self.db
        task_ref = db.collection("chores").document(task_id)
        op_ref = db.collection("operations").document(operation_id)
        today = today_local()
        now = datetime.now(timezone.utc).isoformat()

        @firestore.transactional
        def commit(txn):
            # ALL READS must precede ALL WRITES in Firestore transactions.
            op_snap = op_ref.get(transaction=txn)
            if op_snap.exists:
                old = op_snap.to_dict()
                if (old.get("actor") != actor or old.get("action") != action or
                    old.get("task_id") != task_id or old.get("recipient", "") != recipient or
                    old.get("request_id", "") != request_id):
                    raise Conflict("Operation ID has already been used for another action")
                return old["result"]
            task_snap = task_ref.get(transaction=txn)
            if not task_snap.exists:
                raise Conflict("Unknown chore")
            task = task_snap.to_dict()
            pending = list(task.get("pending_request_ids") or [])
            if len(pending) > 50:
                raise Conflict("Too many pending requests for this chore")
            related = {rid: db.collection("chore_requests").document(rid) for rid in pending}
            if request_id and request_id not in related:
                related[request_id] = db.collection("chore_requests").document(request_id)
            req_snaps = {rid: ref.get(transaction=txn) for rid, ref in related.items()}
            reqs = {rid: s.to_dict() for rid, s in req_snaps.items() if s.exists}
            if any(rid not in reqs for rid in pending):
                raise Conflict("Inconsistent request history; no action taken")
            assignment = task.get("active_assignment")
            available = chore_available(task, today)
            changes = {}
            req_updates = {}
            new_request = None
            completion = None

            if action in ("CLAIM", "REQUEST", "ACCEPT", "COMPLETE") and not available:
                raise Conflict("This chore is not currently available")
            if action == "CLAIM":
                if assignment:
                    raise Conflict("That chore is already assigned")
                if not age_allowed({"attributes": task.get("attributes", {})}, actor):
                    raise Conflict("Not suitable for independent completion")
                changes["active_assignment"] = actor
                changes["assigned_at"] = now
            elif action == "REQUEST":
                if assignment:
                    raise Conflict("That chore is already assigned")
                if recipient not in MEMBERS or recipient == actor:
                    raise Conflict("Choose a different household member")
                if not age_allowed({"attributes": task.get("attributes", {})}, recipient):
                    raise Conflict("That chore is not independently suitable for the recipient")
                if any(r["to"] == recipient and r["status"] == "pending" for r in reqs.values()):
                    raise Conflict("That person already has a pending request")
                new_request = operation_id
                changes["pending_request_ids"] = pending + [new_request]
            elif action in ("ACCEPT", "DECLINE"):
                req = reqs.get(request_id)
                if not req or req.get("status") != "pending" or req["task_id"] != task_id or req["to"] != actor:
                    raise Conflict("No pending request addressed to you")
                if action == "ACCEPT":
                    if not available or assignment:
                        raise Conflict("This chore is no longer available")
                    changes["active_assignment"] = actor
                    changes["assigned_at"] = now
                    req_updates[request_id] = "accepted"
                else:
                    req_updates[request_id] = "declined"
                    changes["pending_request_ids"] = [rid for rid in pending if rid != request_id]
            elif action == "RELEASE":
                if assignment != actor:
                    raise Conflict("You do not own that assignment")
                changes["active_assignment"] = None
                changes["assigned_at"] = None
            elif action == "COMPLETE":
                if assignment and assignment != actor:
                    raise Conflict("Assigned to another household member")
                if not age_allowed({"attributes": task.get("attributes", {})}, actor):
                    raise Conflict("Not suitable for independent completion")
                completion = operation_id
                changes["last_completed_on"] = today.isoformat()
                changes["last_completion_id"] = completion
                changes["active_assignment"] = None
                changes["assigned_at"] = None

            if action in ("CLAIM", "ACCEPT", "COMPLETE"):
                for rid, r in reqs.items():
                    if r.get("status") == "pending":
                        req_updates[rid] = "accepted" if action == "ACCEPT" and rid == request_id else "closed"
                changes["pending_request_ids"] = []

            # Every action writes the chore to serialize concurrent operations.
            changes["activity_updated_at"] = now
            txn.update(task_ref, changes)
            for rid, status in req_updates.items():
                txn.update(related[rid], {"status": status, "resolved_at": now})
            if new_request:
                txn.create(db.collection("chore_requests").document(new_request), {
                    "task_id": task_id, "from": actor, "to": recipient,
                    "note": note, "status": "pending", "created_at": now})
            if completion:
                txn.create(db.collection("completions").document(completion), {
                    "task_id": task_id, "completed_on": today.isoformat(),
                    "area_at_completion": task["area"],
                    "chore_at_completion": task["name"],
                    "notes": note, "completed_by": actor,
                    "source": "household_companion_v2", "created_at": now})
            result = {"saved": True, "action": action, "task_id": task_id,
                      "request_id": new_request or request_id or None,
                      "date": today.isoformat() if completion else None}
            txn.create(op_ref, {"actor": actor, "action": action, "task_id": task_id,
                                "recipient": recipient, "request_id": request_id,
                                "result": result, "created_at": now})
            return result

        return commit(db.transaction())
