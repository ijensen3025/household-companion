"""Pure, testable business logic matching Household Chore Tracker's layout."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

PRIORITY_ORDER = {"High": 0, "Routine": 1, "Flexible": 2, "As needed": 3}

def parse_sheet_date(value: Any):
    """Sheets formatted/unformatted dates: ISO date, US date, or serial number."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) or (isinstance(value,str) and value.replace(".","",1).isdigit()):
        return date(1899, 12, 30) + timedelta(days=int(float(value)))
    v = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None

def build_chores(tasks, history, today=None):
    today = today or datetime.now(ZoneInfo("America/Chicago")).date()
    most_recent = {}
    completed_today_ids = set()
    for row in history:
        if len(row) < 2:
            continue
        completed = parse_sheet_date(row[0])
        task_id = str(row[1]).strip()
        if completed == today:
            completed_today_ids.add(task_id)
        if completed and task_id and (task_id not in most_recent or completed > most_recent[task_id]):
            most_recent[task_id] = completed

    chores = []
    for row in tasks:
        row = list(row) + [""] * (5 - len(row))
        task_id, area, name, frequency, priority = [str(x).strip() for x in row[:5]]
        if not task_id or not name:
            continue
        try:
            interval = int(float(frequency)) if frequency else None
            if interval is not None and interval <= 0:
                interval = None
        except ValueError:
            interval = None
        last = most_recent.get(task_id)
        next_date = last + timedelta(days=interval) if last and interval else None
        if task_id in completed_today_ids:
            status = "Completed today"
        elif last is None:
            status = "Not established"
        elif interval is None:
            status = "Completed as needed"
        elif next_date < today:
            status = "Overdue"
        elif next_date == today:
            status = "Suggested today"
        else:
            status = "Upcoming"
        chores.append({
            "id": task_id, "area": area, "name": name,
            "frequency_days": interval, "priority": priority,
            "last_completed": last.isoformat() if last else None,
            "next_suggested": next_date.isoformat() if next_date else None,
            "status": status, "completed_today": task_id in completed_today_ids,
        })
    return chores

def summary(chores, history):
    return {
        "total": len(chores),
        "areas": len({c["area"] for c in chores}),
        "completions": sum(bool(r and len(r)>1 and str(r[1]).strip()) for r in history),
        "suggested": sum(c["status"] in ("Overdue", "Suggested today") for c in chores),
        "unestablished": sum(c["status"] == "Not established" for c in chores),
        "completed_today": sum(c["completed_today"] for c in chores),
    }

def suggestions(chores, energy="medium", minutes=20):
    """Gentle suggestions, not obligations. Estimated minutes are *heuristics*."""
    energy = energy if energy in ("low", "medium", "high") else "medium"
    budget = max(5, min(int(minutes), 180))
    allowance = {"low": 1, "medium": 2, "high": 4}[energy]
    def estimate(chore):
        name = chore["name"].lower()
        if any(s in name for s in ("deep clean", "declutter", "organize garage", "scrub floor")): return 35
        if any(s in name for s in ("mop", "vacuum", "wash sheets", "change sheets")): return 15
        return 7
    due = [c for c in chores if not c["completed_today"] and c["status"] in ("Overdue", "Suggested today")]
    due.sort(key=lambda c: (
        PRIORITY_ORDER.get(c["priority"], 4),
        c["next_suggested"] or "9999",
        estimate(c), c["area"], c["name"]
    ))
    chosen, used = [], 0
    for c in due:
        mins = estimate(c)
        if len(chosen) >= allowance or used + mins > budget:
            continue
        chosen.append({**c, "estimated_minutes": mins})
        used += mins
    return chosen



def frequency_tab(interval):
    """Classify a task in exactly one completion-frequency tab.

    Valid intervals in the current 129-chore source are 1, 7, 14, 30, 60,
    90, 180 and 365 days, plus blank (as needed). The ranges allow future
    edits without silently dropping chores.
    """
    if interval is None:
        return "as_needed"
    if interval == 1:
        return "daily"
    if 2 <= interval <= 14:
        return "weekly"
    if 15 <= interval <= 45:
        return "monthly"
    if 46 <= interval <= 120:
        return "quarterly"
    return "yearly"


def view_membership(chore, today=None):
    """Return *exactly one* active tab for each chore.

    A scheduled task stays completed strictly before its next suggested date;
    on that date (inclusive) it returns to To Do. A never-completed task goes
    to To Do without being called overdue. As-needed tasks have no scheduled
    return date, so recorded ones stay in Completed As Needed.
    """
    today = today or datetime.now(ZoneInfo("America/Chicago")).date()
    last = parse_sheet_date(chore.get("last_completed"))
    due = parse_sheet_date(chore.get("next_suggested"))
    interval = chore.get("frequency_days")
    is_done = last is not None and (interval is None or (due is not None and due > today))
    selected = frequency_tab(interval) if is_done else "todo"
    return {name: name == selected for name in (
        "todo", "daily", "weekly", "monthly", "quarterly", "yearly", "as_needed"
    )}
