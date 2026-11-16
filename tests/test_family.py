from app.family import fold_events, validate_action, age_allowed, new_event
from app.attributes import recommend
import pytest


def c(id, status="Suggested today", age="All ages", area="Kitchen"):
    return {"id": id, "name": "Wipe counter", "area": area, "priority": "High",
            "status": status, "views": {"todo": True}, "next_suggested": "2026-11-15",
            "attributes": {"physical_effort": "Low", "mental_effort": "Low",
                "estimated_minutes": 5, "age_suitability": age}}


def event(action, actor, task, target="", req="", eid="x"):
    return [eid, "2026-11-15T00:00:00Z", task, action, actor, target, req, ""]


def test_request_remains_unassigned_until_accepted():
    rows = [event("REQUEST", "Ida", "T001", "Husband", "req1")]
    assigned, requests = fold_events(rows, [c("T001")])
    assert assigned == {}
    assert requests["req1"]["status"] == "pending"
    validate_action("ACCEPT", "Husband", "T001", "", "req1", assigned, requests, {"T001"})
    assigned, requests = fold_events(rows + [event("ACCEPT", "Husband", "T001", "", "req1")], [c("T001")])
    assert assigned["T001"] == "Husband"
    assert requests["req1"]["status"] == "accepted"


def test_claim_closes_pending_request_and_excludes_suggestions():
    rows = [event("REQUEST", "Ida", "T001", "Husband", "req1"), event("CLAIM", "Ida", "T001")]
    assigned, requests = fold_events(rows, [c("T001")])
    assert requests["req1"]["status"] == "closed"
    assert recommend([c("T001"),c("T002")], assignments=assigned)[0]["id"] == "T002"


def test_recipient_only_can_accept():
    rows = [event("REQUEST", "Ida", "T001", "Husband", "req1")]
    a,r = fold_events(rows)
    with pytest.raises(ValueError,match="No pending request"):
        validate_action("ACCEPT", "Ida", "T001", "", "req1", a,r,{"T001"})


def test_child_suitability():
    assert age_allowed(c("T001",age="All ages"),"Daughter")
    assert not age_allowed(c("T001",age="Adults only"),"Daughter")
    assert not age_allowed(c("T001",age="Child with supervision"),"Daughter")
    assert age_allowed(c("T001",age="Child with supervision"),"Daughter",supervised=True)
    assert len(recommend([c("T001",age="Adults only"), c("T002")],member="Daughter"))==1


def test_due_first_then_never_recorded():
    due=c("T002")
    new=c("T001",status="Not established")
    new["next_suggested"]=None
    assert recommend([new,due],energy="high")[0]["id"] == "T002"


def test_only_owner_can_release():
    with pytest.raises(ValueError,match="do not own"):
        validate_action("RELEASE","Ida","T001","","",{"T001":"Husband"},{},{"T001"})


def test_complete_closes_assignee():
    a,r=fold_events([event("CLAIM","Ida","T001"),event("COMPLETE","Ida","T001")],[c("T001")])
    assert not a


def test_no_repeating_completed_task_in_assigned():
    completed = c("T001");completed["views"]={"todo":False}
    a,r=fold_events([event("CLAIM","Ida","T001")],[completed])
    assert not a
