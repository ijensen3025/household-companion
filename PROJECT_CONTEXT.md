# Household Companion — project context and Codex handoff

**Purpose:** Working reference for a coding agent operating on the user's existing local Git repository.

**Last context update:** November 15, 2026.

> **Read this first, then inspect the repository.** This document explains design intent and historical decisions; it is **not** a substitute for reading the current source, Git history, tests, and actual deployment configuration. If they differ, stop and reconcile rather than reverting newer user changes.

## 1. How the user wants development to work (high priority)

- **Only one working repository:** `~/household-companion-v2.4` on the user's Mac. The directory name is historical; do not create a fresh `v2.5` directory for every edit.
- **Edit files in that repository directly.** Don't create ZIP releases, downloadable patches, replacement project folders, or copy-instructions as the normal workflow. A locally running Codex agent is expected to have access to the folder.
- **Never claim local files were edited without verifying the actual working tree.** Earlier ChatGPT responses produced files in a remote sandbox that did *not* automatically update the Mac. That caused substantial frustration.
- **Discuss → implement in existing repo → run tests → review `git diff` → commit when explicitly requested → deploy only when explicitly requested.** Do not automatically commit, push, build, or deploy. Preview deployment also requires approval.
- **Protect the live household data.** Do not rerun the original Google Sheets migration, reset Firestore, or rewrite completion history. A 0%-traffic preview may still read/write the **same production Firestore database**.
- Keep development straightforward and incremental. Prefer exact local edits and verifiable commands to long speculative plans.
- Treat family emails as private configuration: read locally if necessary, but never log, publish, or embed actual addresses in documentation, source, or screenshots.

## 2. Project objective and UX philosophy

A private, low-pressure household chore tracker for three household members (Ida, Husband, Daughter). Helps the family maintain the home without creating a punitive or overwhelming task list. The UI emphasizes **“Progress without pressure”** and **“What feels manageable?”**, flexible suggested dates, time/energy-aware recommendations, and shared responsibility.

Core concepts:

- Chores are organized by household area, frequency, and editable attributes.
- Completion history is durable; a chore returns to To Do automatically when its next suggested date arrives.
- Every member has their **own** planner, authenticated identity, claimed chores, and incoming requests.
- Parents manage chore definitions. Daughter gets only age-eligible actions and content.
- Priorities derive from recurrence and weekday/weekend rules, **not** manually maintained High/Medium/Low priority scores.

## 3. Repository and code architecture

**Repository:** `~/household-companion-v2.4` (already initialized as Git by the user; initial v2.4 baseline and a frequency-tab update were reportedly committed). Verify with `git status`, `git log -5 --oneline`, and file inspection.

At the time the v2.4 source release was generated, the code layout was:

```
Dockerfile
requirements.txt
README.md
app/
  main.py            # FastAPI HTTP routes and write guards
  identity.py        # Google IAP JWT verification and member mapping
  firestore_store.py # Firestore persistence / transactions
  family.py          # family and assignment business logic
  logic.py           # date, recurrence, planning logic
  attributes.py      # chore attribute handling
static/
  index.html
  app.js
  styles.css
scripts/
  verify_cutover.py
 tests/               # pytest unit and integration-style fake Firestore tests
```

**Technology:** Python/FastAPI backend, server-rendered/static HTML+vanilla JavaScript/CSS frontend, Google Cloud Run, Google Cloud Firestore (server-side only), Google Cloud IAP sign-in, Git. Do not introduce a major frontend framework or a new data store merely for dashboard rearranging.

**Important source-of-truth warning:** The source snapshot reviewed while creating this document is the original v2.4 release; the user's **Mac repository has newer changes**. In particular the user applied and committed a **frequency-tab UI patch** after the v2.4 baseline. Inspect the current `static/index.html`, `static/app.js`, `static/styles.css`, and tests rather than assuming the old v2.4 markup is current. The drag-and-drop dashboard code was previously offered as separate `dashboard-layout.js` and `.css` files, but it is **not confirmed** that the user copied/applied them. Check `git status`, files, and runtime behavior before writing new code.

## 4. Google Cloud deployment and security

| Setting | Value |
|---|---|
| Google Cloud project ID | `household-chore-tracker-514819` |
| Google Cloud project number | `116405340329` |
| Region | `us-central1` |
| Cloud Run service | `household-companion` |
| Service account | `household-tracker@household-chore-tracker-514819.iam.gserviceaccount.com` |
| Firestore database name | **`household-tracker`** (NOT `(default)`) |
| Primary app URL | `https://household-companion-7guasll4ea-uc.a.run.app` |
| Prior example preview tag | `firestore-preview` (other deployment tags may have been created later) |
| IAP audience | `/projects/116405340329/locations/us-central1/services/household-companion` |
| App timezone | `America/Chicago` |

Backend requires IAP's signed assertion, maps verified Google emails to fixed members, and should enforce authorization on every write. Family email mappings are env vars, not hardcoded email addresses. Relevant env vars:

- `FIRESTORE_DATABASE=household-tracker`
- `CUTOVER_APPROVED=true`
- `WRITE_ENABLED=true` for production writes; use `false` when intentionally read-only
- `OWNER_EMAIL`, `HUSBAND_EMAIL`, `DAUGHTER_EMAIL` (actual values private)
- `IAP_AUDIENCE=/projects/116405340329/locations/us-central1/services/household-companion`

The service account was given `roles/datastore.user` with a condition scoped to the named database. IAP-secured Web App User permissions were configured for household members independently of the app's `*_EMAIL` settings.

**Current deployment knowledge:** The Firestore cutover was verified on 2026-11-15: revision `household-companion-00013-puf` had 100% traffic when checked. The user subsequently deployed or planned to deploy UI changes. **Do not assume that revision is still live.** Always inspect `gcloud run services describe household-companion --region us-central1 --format='yaml(status.traffic)'` and the target revision's actual settings before deployment/cutover.

Cloud Run source deployment is run from the project **directory containing the Dockerfile**, not from the migration toolkit. A previous attempt failed because `--source .` pointed at the wrong folder. Example *reference only; do not execute without permission*:

```bash
gcloud run deploy household-companion \
  --source . --project household-chore-tracker-514819 --region us-central1 \
  --service-account household-tracker@household-chore-tracker-514819.iam.gserviceaccount.com \
  --no-allow-unauthenticated --iap --no-traffic --tag feature-preview \
  --min-instances 0 --max-instances 2
```

A tagged revision with `--no-traffic` does **not** isolate data; previews share production Firestore unless explicitly redesigned. Before promoting with `gcloud run services update-traffic ... --to-tags ...=100`, verify revision env vars, IAP, permissions, live behavior, and rollback considerations. A rollback to code with a fixed 129-chore assumption may break after new chores are added.

## 5. Firestore migration and current data

Originally data lived in a Google Sheet. On November 15, 2026, migration to Firestore was performed, with verified snapshot counts:

- **129** original chores, stable IDs `T001`–`T129`
- **16** original household areas
- **14** completion records
- **0** legacy family events
- Exact snapshot/marker verification returned `CUTOVER VERIFIED`.

Those numbers are **historical migration counts, not permanent invariants**. The app now supports adding chores and areas, and live completion/request counts can grow. Never enforce a fixed 129-chore count or use the old snapshot to overwrite the live data.

The original Google Sheet remains a historical backup; **Firestore is the operational source of truth**. Do not write new app changes to the spreadsheet. Avoid automatic sync unless specifically designed and requested.

Main Firestore collections (verify in code before relying on exact fields):

| Collection | Purpose |
|---|---|
| `chores/{T###}` | Chore definition, attributes, last completion state, assignment, pending-request metadata |
| `completions/{id}` | Recorded completion history; undo removes active event while preserving audit |
| `chore_requests/{uuid}` | Proposed chores, accept/decline/closed status |
| `operations/{uuid}` | Idempotency journal for writes |
| `completion_undos` | Audit records for undone completions |
| `household_areas` | Parent-created area names |
| `household_metadata/chore_counter` | Transactional chore ID allocation |
| `migration_metadata/initial_google_sheets_v1` | Initial verified import marker |
| `family_events` | Imported legacy events, if any |

Multi-user coordination and completion writes should be **atomic Firestore transactions**; idempotency keys prevent duplicate actions caused by retries. Avoid client-side direct Firebase access: application calls backend endpoints, which use the Cloud Run service account.

## 6. Family roles and permissions

| Capability | Ida | Husband | Daughter |
|---|---|---|---|
| See own planner | Yes | Yes | Yes |
| Claim/release eligible chores | Yes | Yes | Yes, age-filtered |
| Complete eligible chores | Yes | Yes | Yes, age-filtered |
| Receive, accept, decline incoming requests | Yes | Yes | Yes |
| Send chore requests to others | Yes | Yes | **No** |
| Edit chore attributes | Yes | Yes | **No** |
| Create chores | Yes | Yes | **No** |
| Create household areas | Yes | Yes | **No** |
| Undo a completion recorded by self | Yes | Yes | Yes |
| Undo a completion recorded by someone else | Yes | Yes | **No** |

Imported legacy completions without an identifiable author can be undone only by a parent. A daughter should independently claim only chores whose suitability is `All ages` or `Child-specific`; `Child with supervision` needs a separate adult-managed workflow. These checks must be enforced on the **server**, not only by hiding controls.

The old “Planning preview for” dropdown was intentionally removed: the authenticated person always gets their own planner. Do not reintroduce an impersonation or profile-selection mechanism that could bypass identity checks.

For requests: proposing a chore to someone does **not** claim/reserve it for them. The request stays pending until accepted or declined; acceptance becomes an assignment, decline restores it to the general available pool. The user and Husband confirmed they could claim/release and send/accept/decline requests from different Google accounts, with claims persisting across refreshes.

## 7. Recurrence, eligibility, date handling, and prioritization

Supported frequencies include daily (1 day), weekly (7), biweekly (14), monthly (30), quarterly (90), semiannually (180), yearly (365), and As Needed. The original form also supports Every 2 Months (60). The repository's actual `frequency_days` mapping is authoritative; do not silently drop unusual frequencies.

- A completed chore stays in the appropriate Completed view until its **next suggested date**, inclusive: when that date arrives it returns to To Do.
- A chore with no completion history displays **“Not established”** rather than being labeled overdue; it's eligible in To Do.
- Example: biweekly kitchen-floor mop completed Nov 15, 2026 returns to To Do Nov 29, 2026.
- Undo should remove only the latest active completion, retain earlier completions, restore previous last-completed date, and recalculate the correct next date and tab; an audit record tracks the undo. The user authorized parent-anyone, daughter-own-only.

**Recommendation priority policy** (automatic, no manual priority field):

- **Monday–Friday:** eligible daily chores first, then weekly, biweekly, monthly, and less frequent chores.
- **Saturday–Sunday:** **due or overdue biweekly and monthly chores** can outrank eligible daily and weekly chores. *Due today counts.* Never-completed chores do not receive this special weekend boost because there is no established due date.
- Energy level, available minutes, cleaning mode (maintain-house vs. focus-on-room), age suitability, already claimed chores, and pending workflow semantics still constrain recommendations.
- Preserve any legacy manual priority values in the database for compatibility, but do not use them to rank recommendations or reintroduce the priority editor without a new decision.
- Dates/weekday determination should use `America/Chicago`, not a random client browser timezone.

## 8. Tracker tabs — latest user-requested layout

**This change was reportedly applied to the user's Mac repository and committed after v2.4.** Verify the code before modifying it.

Primary frequency tabs:

1. `Daily`
2. `Weekly`
3. `Biweekly`
4. `Monthly`
5. `Occasional` — combines **Quarterly, Semiannually, Yearly**
6. `As Needed`

Each frequency tab has **To Do / Completed** views. A chore belongs to its proper frequency tab; its state changes automatically based on completion/next-due date, or undo. Preserve search and area filters. The separate personal planner recommends across **all** frequencies. Check actual behavior for noncanonical intervals such as 60 days rather than losing chores.

## 9. Current pending development task: draggable main dashboard cards

The user said: **“for now just the main dashboard cards please. update local files please”** and later asked how to transfer this work to Codex so it could edit local files directly.

**Implement in the existing repo; do not build, commit, push, or deploy unless requested.**

Desired behavior:

- Allow the signed-in user to rearrange **main dashboard sections** using drag-and-drop, not individual chores or tabs. Potential section identifiers in v2.4 source:
  - `#family-panel` — Your Chores & Requests
  - `section.planning` — What feels manageable?
  - `section.tasks` — Chore Tracker
  - `#chore-management` — Add Chores & Areas (parents only)
- Preserve the introductory welcome/stats/error area in its current position unless the user requests otherwise. **Only the main cards** move.
- Parent-only cards must remain hidden/inaccessible to Daughter. Reordering must never override authorization.
- The layout should persist across page refreshes **per authenticated household member**. A prior prototype used browser `localStorage` keyed by member; this is acceptable for a first version if clearly labeled **device/browser-local**, not shared across devices. Firestore cross-device preference sync would be a separate explicit design/implementation change.
- Prefer an accessible alternative to drag-and-drop (e.g., move-up/move-down buttons) for keyboard and touch users; keep the existing UI style.
- Preserve working form controls, selection state, and event handlers when moving existing DOM nodes. Test with real dashboard behavior and signed-in role changes.
- The previous ChatGPT produced two files called `dashboard-layout.js` and `dashboard-layout.css` with a browser-local approach, but they **were not confirmed copied into the Mac repository**. Inspect first; implement natively or integrate existing work if found. Avoid a second incompatible implementation.
- Add relevant tests for card order, persistence, hidden adult card, and interactions. Run the project's tests and JS syntax check. Show `git diff` and a summary for approval.

## 10. Tests and practical commands

Run commands from the **existing local repository**:

```bash
cd ~/household-companion-v2.4
git status --short
git log -5 --oneline
python3 -m pytest -q
node --check static/app.js
```

If dependencies are missing, inspect `requirements.txt` and use an existing virtual environment where appropriate. Avoid installing/uninstalling broad global packages. The historical v2.4 release reported 78 tests; later frequency-tab work reported 79 tests, but **run tests locally and report actual counts**, not historical claims.

Review changes:

```bash
git diff --stat
git diff --check
git diff
```

Do not automatically execute the commit/deployment commands. If explicitly requested, `git add ...` and a scoped `git commit -m "..."` save the work locally; **a Git commit alone does not deploy the service**, and a GitHub remote is optional. A direct `gcloud run deploy --source .` builds/deploys code from the current directory.

## 11. Known past pitfalls / things to verify

- **Wrong folder:** previously deployed from `household-firestore-migration`; Buildpacks failed due to missing entrypoint. Always verify `pwd` and `Dockerfile`.
- **Python local install on old Intel Mac:** cryptography source builds failed for lack of OpenSSL; a compatible binary wheel resolved it in the separate migration virtual environment. Do not disturb migration tooling unnecessarily.
- **IAP:** verified audience must use correct **12-digit** project number `116405340329`. `OWNER_EMAIL=YOUR_GOOGLE_EMAIL` placeholder caused an earlier “account not registered” error. Keep real email values in Cloud Run config, not repo.
- **Traffic:** Preview tags and revisions are distinct; `--no-traffic` prevents routing regular traffic to the revision but does not prevent database writes through the tagged URL.
- **Fixed 129 guard:** Old versions assumed exactly 129 chores; v2.4 removed this so parents can add chores. Don't restore the guard.
- **Rollback:** Once live data contains new chores, undo records, or assignments that old code does not understand, an old revision may not be safe to promote without data compatibility review.
- **UI vs backend security:** Daughter's restrictions belong in backend authorization as well as visible controls.
- **State consistency:** Chore completion and undo must not lose previously recorded dates; date-based To Do/Completed placement is derived, not an arbitrary manual status flag.

## 12. Suggested first Codex instruction

> Open `~/household-companion-v2.4`. Read `PROJECT_CONTEXT.md`, `README.md`, inspect `git status`, `git log`, and the current application code. The repo on disk is the source of truth. Implement draggable ordering for **main dashboard cards only**, with a keyboard/touch-friendly move alternative and per-user browser-local persistence. Keep the family permissions, new frequency tabs, planner, and Firestore data model unchanged. Run tests, inspect the UI, and show me `git diff` plus a summary. **Do not create a ZIP, another version folder, Git commit, cloud build, or deployment without my explicit approval.**

---

**Status at handoff:** The user has a functioning Firestore-backed Household Companion and has reportedly committed the latest frequency-tab UI change locally. The next step is to make local source edits through Codex to support dashboard-card arrangement. No code changes are made merely by creating this document.
