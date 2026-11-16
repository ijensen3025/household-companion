# Household Companion v2.4 — Undo completions & add chores/areas

Built on **v2.3** (weekday/weekend frequency-first scheduling, Firestore primary database).
This is a source release **only**. Nothing has been deployed or changed in your
live Firestore data. Run the tests, deploy a tagged preview, then choose when to
promote it.

## New features

- **Undo completion:** Latest recorded completion can be undone by Ida or Husband;
  Daughter can undo only a completion credited to Daughter. Legacy imported
  completions with no author are parent-only. A confirmation prompt appears.
  The backend atomically deletes the completion, preserves its content in a
  `completion_undos` audit record, restores the previous completion date/pointer,
  and the dashboard recalculates the date and correct To Do/Completed tab.
  Undo is offered even in To Do if the latest completion is already due again.
  Undo is blocked if the chore has a new active assignment or pending requests.
  An operation UUID protects against duplicate submission.
- **Add new chores:** Ida and Husband alone can create tasks with a unique, stable
  `T###` ID, an existing area, frequency or As Needed, estimated minutes, effort,
  and age suitability. Initially Not established and in To Do.
  IDs are transactionally allocated using `household_metadata/chore_counter`.
- **Add new areas:** Ida and Husband alone can create new named areas. They
  appear immediately in area selection even before they contain any chores.
- **Permissions:** Buttons/forms hidden for Daughter, and server endpoints
  also enforce adult-only operations; Daughter cannot undo others' completions.
- Removed the fixed 129-chore guard so future new chores are loaded and counted.
- Preserved all v2.3 prioritization and all previous family collaboration features.
- Corrected the fallback IAP audience project number to `116405340329`.

## Test locally

```
python -m pip install -r requirements.txt pytest
python -m pytest -q
node --check static/app.js
```

## Deployment (tagged preview; no automatic promotion)

Download/unzip to `~/Downloads/household-companion-v2.4` then run:

```bash
cd ~/Downloads/household-companion-v2.4
gcloud run deploy household-companion \
  --source . \
  --region us-central1 \
  --service-account household-tracker@household-chore-tracker-514819.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --iap \
  --no-traffic \
  --tag undo-preview \
  --min-instances 0 \
  --max-instances 2
```

**Important:** the preview shares your *real* `household-tracker` Firestore database
with production. Verify the preview revision retains `OWNER_EMAIL`,
`HUSBAND_EMAIL`, `DAUGHTER_EMAIL`, `IAP_AUDIENCE`, `FIRESTORE_DATABASE=household-tracker`,
`CUTOVER_APPROVED=true`, and `WRITE_ENABLED=true`. A tagged preview at 0% traffic
still writes to real Firestore if writes are enabled. Avoid accidental test
completions; use a genuine chore or prepare a reversible test.

To inspect traffic before/after deployment:

```bash
gcloud run services describe household-companion \
  --region us-central1 --format='yaml(status.traffic)'
```

After *you* have tested and approved the preview, promote with:

```bash
gcloud run services update-traffic household-companion \
  --region us-central1 --to-tags undo-preview=100
```

The older v2.2 (or v2.3 if already promoted) revision remains available for
rollback, but new chores created in v2.4 will not work with older versions
because they have a fixed 129-chore guard. **Do not roll back blindly once
new chores or undos have been recorded.**

## Data changes

New collections created lazily only when their first records are written:
`completion_undos`, `household_areas`, `household_metadata`.
Existing chores and completions are not migrated, reset, or rewritten during
build or deploy. No Google Sheets access needed.

## Limits / cautions

- This release's Firestore transaction/permissions logic is covered by local
  fake-Firestore tests. It has **not** been validated on your live Cloud Run
  deployment or by simultaneously writing from multiple devices.
- New custom frequencies cannot yet be edited after creation (choose the
  intended frequency when adding a chore).
- Latest completion only can be undone. Each undo is audit-logged, but there's
  no "redo" action.

---

# Earlier release notes

# Household Companion v2.3 — Frequency-first scheduling

Based on the deployed v2.2 Firestore application. No Firestore migration, schema change,
or data reset is required. This release changes *planner recommendation ranking only*,
not chore due dates, Completed-tab membership, assignments, or family permissions.

## Ranking policy

- Monday–Friday: ready daily (1 day), then weekly (2–7 days), then biweekly
  (8–14 days), then monthly (15–45 days), then quarterly/longer, then as-needed.
- Saturday/Sunday: **due or overdue** biweekly (8–14 days) and monthly
  (15–45 days) rise above ready daily and weekly chores. Within the boosted
  tier biweekly comes before monthly.
- Never-completed chores are still eligible but **do not get a weekend boost**,
  since they have no established due date.
- Completed chores return to To Do on their original due date. Filters for
  energy, time, room, age eligibility, and other people's claims are unchanged.
- Existing manual priority values remain in Firestore for compatibility but
  no longer influence recommendations. The edit panel no longer asks adults
  to maintain those values.
- All dates use America/Chicago, obtained once per dashboard request.

## Deploy a preview safely (your v2.2 live app remains at 100%)

1. Extract the ZIP to `~/Downloads/household-companion-v2.3`.
2. Run `cd ~/Downloads/household-companion-v2.3`.
3. Run this from that directory:

```bash
gcloud run deploy household-companion \
  --source . \
  --region us-central1 \
  --service-account household-tracker@household-chore-tracker-514819.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --iap \
  --no-traffic \
  --tag frequency-preview \
  --min-instances 0 \
  --max-instances 2
```

Important: deploying with the service name may inherit latest revision settings;
**verify** `OWNER_EMAIL`, `HUSBAND_EMAIL`, `DAUGHTER_EMAIL`, `IAP_AUDIENCE`,
`FIRESTORE_DATABASE`, `CUTOVER_APPROVED`, and `WRITE_ENABLED` for the new
`frequency-preview` revision before testing. Avoid modifying chore assignments
through the preview until settings are verified. Preview and live revisions
share the same Firestore database, so the test URL is *not* a test database.

After visual verification, use
`gcloud run services update-traffic household-companion --region us-central1 --to-tags frequency-preview=100`
to promote. Keep the previous live revision name for rollback; reconciling any
post-promotion completions would be necessary before restoring the old version.

## Tests

```bash
python -m pytest -q
node --check static/app.js
```

## v2.2: Family role permissions

- Ida and Husband can edit chore attributes (estimated minutes, effort, age suitability, priority).
- Daughter cannot edit attributes or send chore requests. Controls are hidden from her page, and the backend rejects these actions even if an API request is crafted manually.
- Daughter can still claim/release age-eligible chores, complete chores, and accept/decline incoming requests.
- No Firestore schema change or migration required. Deploy this package to the tagged preview using `--no-traffic`.

## v2.1: Individual household planners

The “What feels manageable?” planner is available to every signed-in family member. The “Planning preview for” selection has been removed. Recommendations and claim actions are scoped to the authenticated household member; the server no longer accepts a `preview_for` query parameter. No data migration or Firestore schema change is necessary.

# Household Companion v2.0 — Firestore edition

**Status: source package only. No Cloud Run deployment or database writes have been performed by the package creator.**

This is a replacement for the v1.6 Google Sheets application. Firestore is the **sole operational source of truth** after cutover. The old Google Sheet is retained as a historical backup, not a second editable database.

## Environment / migration

- Google Cloud project: `household-chore-tracker-514819`
- Cloud Run service: `household-companion` (`us-central1`)
- Firestore database (named, **not** `(default)`): `household-tracker`
- Original Google Sheet: kept unchanged
- Existing import: 129 chores, 14 completions, zero family events (verified by prior migration utility)
- Runtime service account: `household-tracker@household-chore-tracker-514819.iam.gserviceaccount.com`
- Google login: Cloud Run **IAP must remain enabled**; application also verifies signed IAP JWTs

### What's implemented

- Same 7 To Do / Completed frequency tabs and automatic return on the **next suggested date (inclusive)**
- Existing energy-aware plans, area focus, editable chore estimates/effort/suitability/priority
- Verified household identity via Google IAP: Ida, Husband, Daughter (individual Google accounts required for independent interactions)
- Unassigned chore requests remain in To Do with pending labels; recipient may accept or decline
- Atomic claims, accept/decline, release, and completion operations in Firestore transactions
- Completion updates the chore's last-completed date and inserts a completion event in a **single transaction**
- UUID operation keys prevent duplicated writes after retrying the same request
- All outstanding requests for a chore close when the chore gets claimed or completed
- No client-side Firebase database access; the FastAPI backend accesses Firestore via Cloud Run service-account identity

### Data model

| Firestore collection | Use |
|---|---|
| `chores/{T###}` | Imported tasks and attributes, current assignment, next-eligible derived from `last_completed_on` and `frequency_days`, pending request IDs |
| `completions/{id}` | Imported history plus new immutable completion entries |
| `chore_requests/{uuid}` | Pending, accepted, declined, or closed household requests |
| `operations/{uuid}` | Idempotency journal (actor, action, task, result) |
| `migration_metadata/initial_google_sheets_v1` | Verified source snapshot marker created by migration |
| `family_events/{id}` | Preserved imported legacy event history; new active state uses chore/request documents |

**Assumptions:** Daughter can independently claim only chores marked `All ages` or `Child-specific`. Chores requiring supervision need an adult-managed workflow in a future update. Child users require an eligible Google account and IAP approval for independent access. No family identities are inferred from the selected planning preview.

## Step 1 — Verify the source has not changed (READ ONLY)

Run **before any cutover** with your existing Python 3.11 environment and keyless impersonated Application Default Credentials:

```bash
cd ~/Downloads/household-firestore-migration
source .venv/bin/activate
python ~/Downloads/household-companion-v2.0/scripts/verify_cutover.py \
  --migration-dir ~/Downloads/household-firestore-migration
```

The expected result includes `CUTOVER VERIFIED`, `129 chores`, and `14 completions` (unless you deliberately reconciled newer history). It compares the **live spreadsheet content hash**, the **migration marker**, and every imported document in the 3 source collections.

If it reports a mismatch: **STOP**. Do not re-run the initial migration with `--apply`, do not delete Firestore documents, and do not cut over. Any Google Sheet edits made since import need to be reconciled deliberately first.

## Step 2 — Prepare Google Cloud identity / permissions

- The service account must have `roles/datastore.user` on the named database (previously granted, with a database-scoped IAM condition).
- The same account needs no Google Sheets API access for **v2 application requests**.
- Ensure IAP is still enabled in Cloud Run Security.
- Configure **`OWNER_EMAIL`** as Ida's Google account email, the one granted access in IAP.
- If Husband or Daughter will sign in separately, later configure `HUSBAND_EMAIL` and `DAUGHTER_EMAIL`, and grant those emails the **IAP-secured Web App User** role on the service. Do not use shared Google logins as a way to simulate identities.
- `IAP_AUDIENCE` defaults to `/projects/11640540329/locations/us-central1/services/household-companion`. If Google reports a JWT-audience mismatch, check the value from official Google Cloud IAP configuration before overriding it.

## Step 3 — Deploy a protected, READ-ONLY candidate (0% of normal traffic)

Do this only after the verification in Step 1 succeeds. Extract the ZIP as `household-companion-v2.0` under Downloads and run:

```bash
cd ~/Downloads/household-companion-v2.0
gcloud run deploy household-companion \
  --source . \
  --region us-central1 \
  --service-account household-tracker@household-chore-tracker-514819.iam.gserviceaccount.com \
  --update-env-vars FIRESTORE_DATABASE=household-tracker,CUTOVER_APPROVED=true,WRITE_ENABLED=false,OWNER_EMAIL=YOUR_GOOGLE_EMAIL \
  --no-allow-unauthenticated \
  --iap \
  --no-traffic \
  --tag firestore-preview \
  --min-instances 0 \
  --max-instances 2
```

**Replace `YOUR_GOOGLE_EMAIL` before running.** Never remove the IAP or authentication flags. This creates a separate, tagged, read-only candidate; the prior Google Sheets revision keeps serving 100% of ordinary traffic. The tagged URL still requires authorization. Do not claim/complete anything in candidate until the cutover.

Check the returned tagged revision URL and verify:

- Signed-in Ida can load the dashboard and sees 129 chores, 16 areas, and 14 completions.
- The frequency tabs, room-focused planning, and time/effort recommendations work.
- All write endpoints return **503 (read-only preview)**.
- Unauthenticated and unregistered Google accounts cannot retrieve chore data.

## Step 4 — Explicit cutover (separate action, not part of this build)

At cutover: stop recording chores in the old app/Sheet, repeat the Step 1 parity check, then deploy the same source again **with** `WRITE_ENABLED=true`, `CUTOVER_APPROVED=true`, and the correct sign-in settings. A normal deployment routes ordinary traffic to the new revision. Verify revision traffic and sign-in immediately. Retain the read-only Google Sheet as backup.

**Do not switch back to the old Google Sheets revision after writing new Firestore completions without first reconciling those records.** The sheet will not be automatically synchronized after cutover.

If service configuration or Google IAP identity verification differs, test and correct in the read-only candidate rather than turning off authentication.

## Development / tests

Python 3.11+ is recommended. Dependencies are installed from `requirements.txt`. On the older Intel macOS machine, pinned cryptography wheels may be necessary; the deployed Cloud Run container uses Linux wheels and does not rely on local macOS compilation.

```bash
python -m pip install -r requirements.txt
python -m pytest -q
node --check static/app.js
```

In restricted offline environments the tests use a minimal Firestore transaction mock (not a live Firestore emulator). **Unit tests are not proof of real Firebase IAM permissions or signed IAP authentication.** The read-only candidate test is required.

## Security and operational caveats

- Identity comes from *verified* IAP JWTs, not from a self-selected `Who's planning?` control.
- The dashboard is served only to registered accounts in the app; IAP also remains the upstream gate.
- Writes are protected by `WRITE_ENABLED=true` in addition to origin and IAP checks. There is no route in the app to toggle this flag from a browser.
- Google Firestore transactions handle contention, but simultaneous claims must be verified against the actual database as part of deployment testing.
- The browser uses random UUID operation IDs for mutations; retries with the **same ID** are idempotent. Repeated new completion attempts on the same day are rejected by business rules.
- Stored family requests and operation journals contain household activity metadata. Review retention, backups, and operational monitoring before wider use.
- Google Cloud can charge for operations; existing budget alerts are not hard spending limits.
