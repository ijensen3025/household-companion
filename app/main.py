"""Household Companion v2: Firestore primary backend + verified Google IAP identity."""
import os
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from .firestore_store import FirestoreStore, Conflict
from .identity import member_for_request
from .attributes import EFFORT, AGE, PRIORITIES

BASE = Path(__file__).resolve().parent.parent
app = FastAPI(title="Household Companion v2", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

@app.middleware("http")
async def disable_caching(request: Request, call_next):
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith(("/static/", "/api/")):
        resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp

class AttributeUpdate(BaseModel):
    estimated_minutes: int = Field(ge=1, le=240)
    physical_effort: str
    mental_effort: str
    age_suitability: str
    priority: str

class ChoreAction(BaseModel):
    task_id: str = Field(pattern=r"^T\d{3,}$")
    action: str
    operation_id: str
    recipient: str = ""
    request_id: str = ""
    note: str = Field(default="", max_length=200)

class Completion(BaseModel):
    task_id: str = Field(pattern=r"^T\d{3,}$")
    operation_id: str
    note: str = Field(default="Completed in Household Companion", max_length=240)

class UndoCompletion(BaseModel):
    task_id: str = Field(pattern=r"^T\d{3,}$")
    completion_id: str = Field(min_length=1, max_length=180)
    operation_id: str

class AreaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=70)

class ChoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    area: str = Field(min_length=1, max_length=70)
    frequency_days: int | None = Field(default=None, ge=1, le=3650)
    estimated_minutes: int = Field(ge=1, le=240)
    physical_effort: str
    mental_effort: str
    age_suitability: str

def store():
    if os.environ.get("FIRESTORE_DATABASE") != "household-tracker":
        raise HTTPException(503, "Firestore database is not configured")
    if os.environ.get("CUTOVER_APPROVED") != "true":
        raise HTTPException(503, "Firestore cutover has not been approved")
    return FirestoreStore()

def writable():
    if os.environ.get("WRITE_ENABLED") != "true":
        raise HTTPException(503, "Firestore preview is read-only until cutover")

def current_member(request):
    # Never allow unverified identity to fall back to shared Ida privileges.
    return member_for_request(request)

def guard_write(request):
    if request.headers.get("x-household-request") != "1":
        raise HTTPException(403, "Missing request header")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Expected application/json")
    origin = request.headers.get("origin")
    host = request.headers.get("host", "")
    if not origin or urlsplit(origin).netloc.lower() != host.lower() or urlsplit(origin).scheme != "https":
        raise HTTPException(403, "Cross-origin request blocked")

@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")

@app.get("/api/chores")
def get_chores(request: Request, energy: str="medium", minutes: int=20,
               mode: str="maintain", room: str=""):
    actor = current_member(request)
    try:
        return store().dashboard(actor, energy, minutes, mode, room)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Could not read the Firestore database")

@app.post("/api/attributes/{task_id}")
def save_attributes(task_id: str, payload: AttributeUpdate, request: Request):
    guard_write(request)
    writable()
    if current_member(request) not in ("Ida", "Husband"):
        raise HTTPException(403, "Only adult household members can edit shared chore attributes")
    if not (task_id.startswith("T") and len(task_id) >= 4 and task_id[1:].isdigit()):
        raise HTTPException(400, "Invalid Task ID")
    if payload.physical_effort not in EFFORT or payload.mental_effort not in EFFORT or payload.age_suitability not in AGE or payload.priority not in PRIORITIES:
        raise HTTPException(422, "Invalid attribute value")
    try:
        store().save_attributes(task_id, payload.model_dump())
        return {"saved": True, "task_id": task_id}
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Could not update chore attributes")

@app.post("/api/complete")
def complete(payload: Completion, request: Request):
    guard_write(request)
    writable()
    actor = current_member(request)
    try:
        return store().change("COMPLETE", actor, payload.task_id, payload.operation_id, note=payload.note)
    except (Conflict, ValueError) as exc:
        raise HTTPException(409, str(exc))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Could not complete chore")

@app.post("/api/family/action")
def family_action(payload: ChoreAction, request: Request):
    guard_write(request)
    writable()
    actor = current_member(request)
    if payload.action not in ("REQUEST", "ACCEPT", "DECLINE", "CLAIM", "RELEASE"):
        raise HTTPException(422, "Unsupported action")
    if actor == "Daughter" and payload.action == "REQUEST":
        raise HTTPException(403, "Child household members cannot send chore requests")
    try:
        return store().change(payload.action, actor, payload.task_id, payload.operation_id,
                              payload.recipient, payload.request_id, payload.note)
    except (Conflict, ValueError) as exc:
        raise HTTPException(409, str(exc))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Could not update chore assignment or request")

@app.post("/api/completions/undo")
def undo_completion(payload: UndoCompletion, request: Request):
    guard_write(request)
    writable()
    actor = current_member(request)
    try:
        return store().undo_completion(actor, payload.task_id, payload.operation_id, payload.completion_id)
    except (Conflict, ValueError) as exc:
        raise HTTPException(409, str(exc))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Could not undo completion")

@app.post("/api/areas")
def create_area(payload: AreaCreate, request: Request):
    guard_write(request)
    writable()
    actor = current_member(request)
    if actor not in ("Ida", "Husband"):
        raise HTTPException(403, "Only parents can add household areas")
    try:
        return store().create_area(actor, payload.name)
    except (Conflict, ValueError) as exc:
        raise HTTPException(409, str(exc))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Could not create area")

@app.post("/api/chores")
def create_chore(payload: ChoreCreate, request: Request):
    guard_write(request)
    writable()
    actor = current_member(request)
    if actor not in ("Ida", "Husband"):
        raise HTTPException(403, "Only parents can add chores")
    try:
        return store().create_chore(actor, payload.model_dump())
    except (Conflict, ValueError) as exc:
        raise HTTPException(409, str(exc))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Could not create chore")
