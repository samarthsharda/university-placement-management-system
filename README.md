# University Placement Management System

A working academic implementation of the accompanying Service Oriented Architecture case study. Built with Python, FastAPI, SQLite, and a local HTML/CSS/JavaScript interface.

## Start on Windows

1. Extract the complete ZIP into a folder.
2. Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/) if it is not already installed. Enable the Python launcher during installation.
3. Double-click **Start-Placement.cmd**. On this computer, the launcher can also use Codex's bundled Python if a separate Python installation is unavailable.
4. On the first run, the launcher creates a private Python environment and downloads the required libraries. Keep its window open while using the app.
5. Open [the placement app](http://127.0.0.1:8020). If the browser opens before the server is ready, refresh once.

Stop with **Ctrl+C** in the server window. Subsequent starts preserve your records. Internet is required for initial library installation and the default Swagger documentation assets; the application interface itself uses local assets.

If Windows blocks a downloaded ZIP, open its Properties and choose Unblock before extraction. You can also run the manual commands below without the launcher.

## Demo accounts

All seeded accounts use the password **Placement@123**.

| Role | Email | Scope |
| --- | --- | --- |
| Placement officer | officer@demo.edu | Academic verification, approvals, all workflows, reports and service console |
| Recruiter | recruiter@demo.edu | Northstar Technologies drives and applicants |
| Second recruiter | recruiter2@demo.edu | Vertex Labs drives and applicants |
| Students | s01@demo.edu through s06@demo.edu | Own profile, applications, interviews, offers and notifications |

These are local demo identities. They are not real university accounts. All student and company records are fictional.

## What works

- Sign-in with hashed passwords, expiring bearer sessions, logout, and server-enforced role and record scope.
- Six students matching the report's cohort, including the exact CGPA threshold and an unverified profile.
- Recruiter-created draft drives, officer approval, publication, closure and versioned policies.
- Explainable eligibility previews and a fresh check inside the application transaction.
- Unique applications, idempotent retries, immutable academic/policy evidence and optional private PDF resumes.
- Shortlisting, selection, rejection and student withdrawal with state/version checks.
- Interview reservations with concurrent student, room and interviewer conflict protection.
- Offer issue, student acceptance/decline, expiry checks, staff revocation and a one-accepted-offer invariant.
- Durable outbox, independent consumers, simulated delivery outage, three-attempt dead letters and safe replay.
- Event-driven reports, defined denominators, source reconciliation, CSV export and audit history.
- An SOA console and generated [OpenAPI contract](http://127.0.0.1:8020/openapi.json). Interactive [API documentation](http://127.0.0.1:8020/docs) is also available.

## Present the implementation

Follow [DEMO_GUIDE.md](DEMO_GUIDE.md) for a step-by-step classroom demonstration and viva explanations. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the service boundaries, transaction choices and report alignment. Actual browser screenshots are in [docs/screenshots](docs/screenshots).

## Manual setup

From this project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8020
```

On macOS/Linux, use `python3 -m venv .venv`, `.venv/bin/python` and the same pip/uvicorn arguments.

The SQLite database and resume versions are created under `data/` on first start. Set `PLACEMENT_DB` to an absolute SQLite path to isolate another demonstration.

## Run the worker

By default, dispatch is deliberately manual so you can show eventual consistency and failure recovery. The officer's **SOA service console → Process queued events** button invokes the same consumer logic as the separate worker:

```powershell
.\.venv\Scripts\python.exe worker.py
# Or keep polling every five seconds:
.\.venv\Scripts\python.exe worker.py --watch
```

The worker must use the same `PLACEMENT_DB` setting as the server. Stop an automatic worker before demonstrating manual dead-letter attempts.

## Automated checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
```

The acceptance suite has 16 tests covering the report's T1–T9 scenarios plus identity, immutable snapshots, drive lifecycle, uploads, reporting calculations, cohort filtering and restart persistence. Tests use isolated databases. The concurrency checks coordinate genuinely simultaneous requests with barriers. See [the verification record](docs/VALIDATION.md) for the completed checks and browser evidence. `requirements-lock.txt` preserves the exact application dependency versions used for validation.

## Reset for a fresh demonstration

Stop the server and worker first, then run:

```powershell
.\.venv\Scripts\python.exe reset_demo.py --confirm
```

Existing demo data is archived, not deleted. The next start seeds the original six students, D101 published and D102 draft, with no applications. Deadlines are generated relative to first initialization, so the initial demo is not tied to the report's dates.

## Implementation boundaries

This is a **modular SOA demonstration in one process with one SQLite database**. Logical services have separate modules and API contracts. They are not independently deployed microservices. Local composition and shared transactions intentionally simplify the distributed admission/reservation problem described in the report.

Institutional OIDC and ERP connectors, real email/SMS, antivirus scanning, a network message broker, HA, distributed sagas, arbitrary report periods, bulk import, production monitoring, load certification and backup restoration are not implemented. Academic verification is manual, notifications appear in the in-app inbox, and the outbox uses SQLite. The system is for a local academic demonstration; do not expose its seeded credentials to the internet.

## Source layout

```text
app/main.py                  FastAPI gateway, identity adapter, service catalogue
app/contracts.py             Validated input contracts
app/security.py              Identity, sessions and access scopes
app/db.py                    Schema, transactions and fictional seed records
app/services/profiles.py     Profile ownership and academic versions
app/services/drives.py       Drive lifecycle and policy versions
app/services/eligibility.py  Reusable decision rules
app/services/applications.py Submission, evidence and idempotency
app/services/scheduling.py   Calendar conflict checks
app/services/offers.py       Offer states and exclusive acceptance
app/services/events.py       Outbox, notification consumer and replay
app/services/reporting.py    Read model, reconciliation and CSV
app/services/resumes.py      Private PDF versions
app/static/                  Browser interface with no frontend build step
tests/test_workflows.py      Executable acceptance checks
worker.py                    Optional separate local consumer process
```
