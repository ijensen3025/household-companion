from datetime import date
from app.attributes import (HEADERS, default_attributes, merge_attributes,
                            parse_attributes, recommend)
from app.logic import build_chores, view_membership


def chore(name="Mop floor", area="Kitchen", task_id="T058", priority="Routine"):
    c = {"id": task_id, "name": name, "area": area, "priority": priority,
         "status": "Not established", "completed_today": False}
    c["views"] = {"todo": True}
    return c


def test_starter_attributes_are_conservative():
    d = default_attributes(chore())
    assert d["estimated_minutes"] == 15
    assert d["physical_effort"] == "Medium"
    assert d["age_suitability"] == "Adults only"


def test_chore_attributes_schema_and_priority_remains_master():
    c = chore()
    values = [HEADERS, ["T058", "Mop floor", 22, "High", "Medium", "Adults only", "High"]]
    stored = parse_attributes(values)
    enriched = merge_attributes([c], stored)[0]
    assert enriched["attributes"]["estimated_minutes"] == 22
    assert enriched["attributes"]["priority"] == "Routine"


def test_low_energy_filters_high_physical_effort():
    a = chore("Wipe counters", task_id="T056", priority="High")
    b = chore("Vacuum stairs", task_id="T079")
    enriched = merge_attributes([a,b], None)
    assert [c["id"] for c in recommend(enriched, energy="low", minutes=20)] == ["T056"]


def test_room_focus_only_considers_selected_area():
    a = chore("Wipe counters", task_id="T056")
    b = chore("Wipe coffee table", area="Main living room", task_id="T040")
    enriched = merge_attributes([a,b], None)
    assert [c["id"] for c in recommend(enriched, mode="room", room="Kitchen")] == ["T056"]


def test_completed_chore_never_recommended_before_due():
    rows = [["T058", "Kitchen", "Mop floor", 14, "Routine"]]
    history = [["2026-11-15", "T058"]]
    c=build_chores(rows,history,today=date(2026,11,16))[0]
    c["views"]=view_membership(c,date(2026,11,16))
    assert recommend(merge_attributes([c],None)) == []
    c["views"]=view_membership(c,date(2026,11,29))
    assert [x["id"] for x in recommend(merge_attributes([c],None))] == ["T058"]


def test_invalid_or_uninitialized_sheet():
    import pytest
    with pytest.raises(ValueError, match="must contain"):
        parse_attributes(None)
    with pytest.raises(ValueError, match="must contain"):
        parse_attributes([["Wrong", "Header"]])
    with pytest.raises(ValueError, match="Estimated minutes"):
        parse_attributes([HEADERS,["T058","Mop floor",0,"Low","Low","Adults only","Routine"]])


def test_imported_final_sheet_structure_and_new_age_groups():
    rows=[HEADERS, ["T001", "Clean toilet", 2, "Low", "Low", "All ages", "High"],
          ["T002", "Wipe sink", 5, "Low", "Low", "Child-specific", "Routine"]]
    out=parse_attributes(rows)
    assert out["T001"]["estimated_minutes"] == 2
    assert out["T002"]["age_suitability"] == "Child-specific"

