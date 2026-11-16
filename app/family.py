"""Pure family assignment/request logic; store events in a separate append-only sheet."""
from datetime import datetime
from uuid import uuid4

MEMBERS = ("Ida", "Husband", "Daughter")
HEADERS = ["Event ID", "Timestamp UTC", "Task ID", "Action", "Actor", "Recipient", "Request ID", "Notes"]
ACTIONS = {"REQUEST", "ACCEPT", "DECLINE", "CLAIM", "RELEASE", "COMPLETE"}


def fold_events(rows, chores=None):
    """Compute current state, excluding requests for completed/claimed tasks."""
    assigned, requests = {}, {}
    for row in rows:
        f = list(row) + [""] * 8
        event_id, timestamp, task, action, actor, recipient, request_id, note = [str(v).strip() for v in f[:8]]
        if not event_id or action not in ACTIONS or not task:
            continue
        if action == "REQUEST":
            requests[request_id or event_id] = {"id": request_id or event_id, "task_id": task,
                "from": actor, "to": recipient, "note": note, "status": "pending"}
        elif action in ("ACCEPT", "DECLINE"):
            req = requests.get(request_id)
            if req and req["status"] == "pending":
                if action == "ACCEPT" and not assigned.get(task):
                    req["status"] = "accepted"
                    assigned[task] = actor
                elif action == "DECLINE":
                    req["status"] = "declined"
        elif action == "CLAIM":
            if task not in assigned:
                assigned[task] = actor
        elif action in ("RELEASE", "COMPLETE"):
            if assigned.get(task) == actor or action == "COMPLETE":
                assigned.pop(task, None)
        if action in ("ACCEPT", "CLAIM", "COMPLETE"):
            for req in requests.values():
                if req["task_id"] == task and req["status"] == "pending":
                    req["status"] = "closed"
    if chores is not None:
        available = {c["id"] for c in chores if c.get("views", {}).get("todo")}
        for task in list(assigned):
            if task not in available:
                assigned.pop(task)
        for req in requests.values():
            if req["status"] == "pending" and req["task_id"] not in available:
                req["status"] = "closed"
    return assigned, requests


def validate_action(action, actor, task_id, recipient, request_id, assigned, requests, available):
    if actor not in MEMBERS:
        raise ValueError("Unknown household member")
    if task_id not in available:
        raise ValueError("This chore is not currently available")
    if action == "REQUEST":
        if recipient not in MEMBERS or recipient == actor:
            raise ValueError("Select a different household member")
        if task_id in assigned:
            raise ValueError("That chore is already assigned")
        if any(r["task_id"] == task_id and r["to"] == recipient and r["status"] == "pending"
               for r in requests.values()):
            raise ValueError("This person already has a pending request for that chore")
    elif action == "CLAIM":
        if task_id in assigned:
            raise ValueError("That chore is already assigned")
    elif action in ("ACCEPT", "DECLINE"):
        req = requests.get(request_id)
        if not req or req["status"] != "pending" or req["task_id"] != task_id or req["to"] != actor:
            raise ValueError("No pending request addressed to you")
        if action == "ACCEPT" and task_id in assigned:
            raise ValueError("The chore was already claimed")
    elif action == "RELEASE":
        if assigned.get(task_id) != actor:
            raise ValueError("You do not own that assignment")
    else:
        raise ValueError("Unsupported action")


def new_event(action, actor, task_id, recipient="", request_id="", note=""):
    event_id = str(uuid4())
    return [event_id, datetime.utcnow().isoformat() + "Z", task_id, action,
            actor, recipient, request_id or (event_id if action == "REQUEST" else ""), note]


def age_allowed(chore, member, supervised=False):
    if member != "Daughter":
        return True
    suitability = chore.get("attributes", {}).get("age_suitability")
    return suitability in ("All ages", "Child-specific") or (supervised and suitability == "Child with supervision")
