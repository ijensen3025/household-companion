"""Planner frequency-ranking regression tests on fixed Chicago-local dates."""
from datetime import date, timedelta
from app.attributes import recommend, frequency_rank
from app.logic import build_chores, view_membership

WED = date(2026, 11, 18)
SAT = date(2026, 11, 21)
SUN = date(2026, 11, 22)


def chores_for(day, specs):
    # (task ID, frequency, due-offset in days or None if never recorded, legacy priority)
    rows, history = [], []
    for tid, interval, due_offset, priority in specs:
        rows.append([tid, "Kitchen", tid, interval or "", priority])
        if due_offset is not None:
            history.append([(day + timedelta(days=due_offset - interval)).isoformat(), tid])
    chores = build_chores(rows, history, day)
    for c in chores:
        c["views"] = view_membership(c, day)
        c["attributes"] = {"estimated_minutes": 5, "physical_effort": "Low",
                           "mental_effort": "Low", "age_suitability": "All ages"}
    return chores


def ranked(day, specs, **kwargs):
    return [c["id"] for c in recommend(chores_for(day, specs), today=day,
            energy="high", minutes=120, **kwargs)]


def test_weekday_daily_weekly_always_first_even_if_deep_cleaning_overdue():
    specs = [("T001", 30, -25, "High"), ("T002", 14, -20, "High"),
             ("T003", 7, 0, "Flexible"), ("T004", 1, 0, "Flexible")]
    assert ranked(WED, specs) == ["T004", "T003", "T002", "T001"]


def test_weekend_due_or_overdue_biweekly_and_monthly_beat_daily_weekly():
    specs = [("T001", 1, 0, "High"), ("T002", 7, -3, "High"),
             ("T003", 14, 0, "Flexible"), ("T004", 30, -2, "Flexible")]
    for day in (SAT, SUN):
        assert ranked(day, specs) == ["T003", "T004", "T001", "T002"]


def test_weekend_not_established_deep_cleaning_not_boosted():
    specs = [("T001", 1, 0, "Routine"), ("T002", 14, None, "High"),
             ("T003", 30, None, "High")]
    assert ranked(SAT, specs) == ["T001", "T002", "T003"]


def test_not_yet_due_deeper_cleaning_not_in_todo():
    specs = [("T001", 1, 0, "Routine"), ("T002", 14, 2, "High")]
    assert ranked(SAT, specs) == ["T001"]


def test_weekend_boost_is_only_biweekly_and_monthly():
    specs = [("T001", 1, 0, "Routine"), ("T002", 90, -12, "High"),
             ("T003", 365, -200, "High"), ("T004", 14, -1, "Flexible")]
    assert ranked(SAT, specs) == ["T004", "T001", "T002", "T003"]


def test_priority_attribute_does_not_override_frequency():
    specs = [("T001", 30, -10, "High"), ("T002", 1, 0, "Flexible")]
    assert ranked(WED, specs) == ["T002", "T001"]
    assert ranked(SAT, specs) == ["T001", "T002"]


def test_energy_time_and_assignment_constraints_still_apply():
    cs = chores_for(SAT, [("T001", 14, -1, "High"), ("T002", 1, 0, "Routine")])
    cs[0]["attributes"]["physical_effort"] = "High"
    assert [c["id"] for c in recommend(cs, today=SAT, energy="low", minutes=10)] == ["T002"]
    assert [c["id"] for c in recommend(cs, today=SAT, energy="high", minutes=10,
                         assignments={"T001": "Husband"})] == ["T002"]


def test_follow_local_weekend_date_not_utc_date():
    assert frequency_rank({"frequency_days": 14, "status": "Suggested today",
                            "next_suggested": SAT.isoformat()}, SAT)[0] == 0
    assert frequency_rank({"frequency_days": 14, "status": "Overdue",
                            "next_suggested": WED.isoformat()}, WED)[0] == 3
