"""Chore attribute schema and conservative starter estimates, keyed by stable Task ID.

Initial estimates are editable planning aids, NOT observed task durations, effort,
or individualized assessments of a child. Task priority is owned by Chore Tracker.
"""

HEADERS = ["Task ID", "Chore name", "Estimated time (minutes)", "Physical effort", "Mental effort", "Age suitability", "Priority"]
EFFORT = ("Low", "Medium", "High")
AGE = ("Adults only", "Child with supervision", "All ages", "Child-specific")
PRIORITIES = ("High", "Routine", "Flexible", "As needed", "Daily")

def default_attributes(task):
    name = str(task.get("name", "")).lower()
    area = str(task.get("area", "")).lower()
    mins, physical, mental = 10, "Low", "Low"
    age = "Adults only"  # conservative until an adult reviews each task
    if any(x in name for x in ("behind refrigerator", "behind stove", "carpet clean", "under and behind furniture")):
        mins, physical, mental = 40, "High", "Medium"
    elif any(x in name for x in ("deep clean", "organize garage storage", "declutter garage", "declutter and organize pantry", "declutter and organize refrigerator")):
        mins, physical, mental = 35, "Medium", "High"
    elif any(x in name for x in ("declutter", "organize", "review clothes")):
        mins, physical, mental = 20, "Low", "Medium"
    elif any(x in name for x in ("mop", "vacuum stairs", "sweep garage", "scrub floor", "clean shower", "clean bathtub", "clean toilet")):
        mins, physical = 15, "Medium"
    elif any(x in name for x in ("vacuum", "change sheets", "wash sheets", "break down and manage cardboard")):
        mins, physical = 15, "Medium"
    elif any(x in name for x in ("wipe", "dust", "clean sink", "clean stovetop", "clean microwave", "pick up", "tidy", "empty trash", "recycling")):
        mins = 7
    if "garage" in area and "organize" in name:
        physical, mental = "Medium", "Medium"
    # Only obviously low-risk tidying of the child's own space is initially independent.
    if area == "daughter bedroom" and any(x in name for x in ("organize clothes pile", "dust surfaces", "declutter belongings")):
        age = "All ages" if "organize clothes pile" in name else "Child with supervision"
    elif any(x in name for x in ("pick up and tidy", "organize clothes pile", "declutter bench coats and bags", "declutter and organize frankie school bin")):
        age = "Child with supervision"
    elif any(x in name for x in ("wipe coffee table", "wipe kitchen table", "wipe kitchen chairs")):
        age = "Child with supervision"
    return {"estimated_minutes": mins, "physical_effort": physical,
            "mental_effort": mental, "age_suitability": age,
            "priority": task.get("priority", "Routine")}

def parse_attributes(rows):
    """Parse the seven-column, human-readable imported worksheet.

    Reject a mismatched header or malformed values rather than silently
    substituting generated estimates for Ida's reviewed values.
    """
    if not rows or [str(c).strip() for c in rows[0][:7]] != HEADERS:
        raise ValueError("Chore Attributes must contain: " + ", ".join(HEADERS))
    out = {}
    for sheet_row, row in enumerate(rows[1:], start=2):
        fields = list(row) + [""] * 7
        task_id = str(fields[0]).strip()
        if not task_id:
            continue
        if task_id in out:
            raise ValueError(f"Duplicate Task ID {task_id} in Chore Attributes")
        minutes = fields[2]
        try:
            value = float(minutes)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid estimated minutes for {task_id} (row {sheet_row})")
        if not value.is_integer() or not (1 <= value <= 240):
            raise ValueError(f"Estimated minutes must be a whole number from 1 to 240 for {task_id}")
        physical, mental, age = [str(v).strip() for v in fields[3:6]]
        if physical not in EFFORT or mental not in EFFORT or age not in AGE:
            raise ValueError(f"Invalid effort/age classification for {task_id} (row {sheet_row})")
        out[task_id] = {
            "chore_name": str(fields[1]).strip(),
            "estimated_minutes": int(value), "physical_effort": physical,
            "mental_effort": mental, "age_suitability": age,
            "priority": str(fields[6]).strip(),
        }
    return out

def merge_attributes(chores, stored):
    result = []
    for c in chores:
        d = default_attributes(c)
        if stored and c["id"] in stored:
            d.update({k:v for k,v in stored[c["id"]].items() if k != "priority"})
        d["priority"] = c["priority"]  # authoritative existing Chore Tracker column E
        result.append({**c, "attributes": d})
    return result

def attribute_row(task):
    d = default_attributes(task)
    return [task["id"], task["name"], d["estimated_minutes"], d["physical_effort"],
            d["mental_effort"], d["age_suitability"],
            f'=IFERROR(VLOOKUP(A{task["sheet_row"]},\'Chore Tracker\'!A:E,5,FALSE),"Routine")']

def frequency_rank(chore, today):
    """Rank eligible chores using the household's weekday/weekend routine.

    During the week daily and weekly chores outrank everything else.
    On weekends *due or overdue* biweekly/monthly chores go ahead of
    daily/weekly work; never-completed chores do not receive the weekend boost.

    Frequencies follow existing completion-tab boundaries: daily=1,
    weekly=2..7, biweekly=8..14, monthly=15..45 days.
    """
    from datetime import date
    if isinstance(today, str):
        today = date.fromisoformat(today)
    interval = chore.get("frequency_days")
    established = chore.get("status") != "Not established"
    due = chore.get("next_suggested")
    if due and established:
        due = date.fromisoformat(due)
        due = due <= today
    else:
        due = False
    is_weekend = today.weekday() >= 5
    if is_weekend and due and interval is not None and 8 <= interval <= 45:
        return (0, interval)  # Due/overdue deeper cleaning leads on weekends.
    if interval == 1:
        return (1, 1)
    if interval is not None and 2 <= interval <= 7:
        return (2, interval)
    if interval is not None and 8 <= interval <= 14:
        return (3, interval)
    if interval is not None and 15 <= interval <= 45:
        return (4, interval)
    if interval is not None and interval > 45:
        return (5, interval)
    return (6, 9999)  # As-needed / unknown frequency is flexible.


def recommend(chores, energy="medium", minutes=20, mode="maintain", room=None,
              member="Ida", assignments=None, supervised=False, today=None):
    """Recommend eligible work using frequency and the local weekday/weekend.

    Time, effort, assignment and age restrictions remain hard eligibility filters.
    The legacy manually edited priority field does not affect this ranking.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from .family import age_allowed
    today = today or datetime.now(ZoneInfo("America/Chicago")).date()
    assignments = assignments or {}
    energy = energy if energy in ("low", "medium", "high") else "medium"
    budget = max(5, min(180, int(minutes)))
    max_effort = {"low": 0, "medium": 1, "high": 2}[energy]
    grade = {"Low": 0, "Medium": 1, "High": 2}
    eligible = [c for c in chores if c.get("views", {}).get("todo") and
                c["id"] not in assignments and
                (mode != "room" or c["area"] == room) and age_allowed(c, member, supervised)]
    eligible = [c for c in eligible if
                grade[c["attributes"]["physical_effort"]] <= max_effort and
                grade[c["attributes"]["mental_effort"]] <= max_effort]
    chosen, used, used_areas = [], 0, set()
    max_tasks = {"low": 1, "medium": 3, "high": 5}[energy]
    def order_key(c):
        return (frequency_rank(c, today),
                1 if c["status"] == "Not established" else 0,
                1 if mode == "maintain" and c["area"] in used_areas else 0,
                c.get("next_suggested") or "9999",
                c["attributes"]["estimated_minutes"], c["id"])
    while len(chosen) < max_tasks:
        choices = [c for c in eligible if c["id"] not in {x["id"] for x in chosen}
                   and used + c["attributes"]["estimated_minutes"] <= budget]
        if not choices:
            break
        c = min(choices, key=order_key)
        chosen.append({**c, "estimated_minutes": c["attributes"]["estimated_minutes"]})
        used += c["attributes"]["estimated_minutes"]
        used_areas.add(c["area"])
    return chosen
