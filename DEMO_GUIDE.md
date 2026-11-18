# Classroom Demonstration Guide

Allow about eight to ten minutes. Start with a fresh database so the report's original worked example is easy to reproduce. Use the same password, `Placement@123`, for each account. Keep the optional automatic worker stopped during the event-delivery demonstration.

## 1 Show the system and its boundaries

Sign in as `officer@demo.edu`. Show **Overview**, then **SOA service console**.

Say: “This is a working modular implementation of the university placement case study. The eight logical services expose explicit API contracts. They run locally in one FastAPI process with SQLite. The console shows the actual modules and their contracts.”

Show the eight service cards and the outbox flow. Open API docs if an internet connection is available, or use **View OpenAPI contract** for the locally generated contract.

## 2 Verify the report's eligibility example

Open **Student records**. Show S01–S06, their programmes, CGPA, backlogs and verification. S02 has CGPA exactly 7.00; S06 is unverified.

Open **Placement drives → Evaluate the sample cohort**. Initially D101 yields:

| Student | Result | Reason |
| --- | --- | --- |
| S01 | Eligible | All rules met |
| S02 | Eligible | Inclusive 7.00 threshold |
| S03 | Ineligible | CGPA below minimum |
| S04 | Ineligible | Programme not allowed |
| S05 | Ineligible | Backlog limit exceeded |
| S06 | Review required | Academic record unverified |

Say: “The same Eligibility Service is used for this preview and for the final submission check. Decisions include academic and policy versions and reason codes.”

## 3 Submit two student applications

Sign out. Sign in as `s01@demo.edu`. Open **Placement drives → Check & apply → Submit application**. A resume is optional for the classroom demo. If you want to demonstrate real file upload, first open **My profile**, upload a PDF smaller than 2 MB and choose that version while applying.

Open **Applications → View snapshot**. Show the academic version, policy version, exact academic fields, rule snapshot and evaluation time. The successful response is durable even before notification delivery.

Repeat as `s02@demo.edu`. Their exact boundary CGPA still permits submission. If asked about repeated clicks, explain the idempotency key and unique student/drive constraint; the automated suite exercises concurrent duplicate requests.

## 4 Demonstrate recruiter scope and workflow

Sign in as `recruiter2@demo.edu`. **Applications** is empty because these applications belong to Northstar, not Vertex.

Sign in as `recruiter@demo.edu`. Open **Applications**, shortlist both students, then open **Interviews → Schedule interview**. Choose an applicant, a future start/end, an interviewer and a room. After saving, attempt a second interview at the same time in the same room. The service rejects the conflict. Choose a non-overlapping time to continue.

Say: “The availability check and reservation are serialized in the Scheduling Service's transaction. The database protects simultaneous requests; a browser-only check would be insufficient.”

Return to **Applications** and select both shortlisted students. Open **Offers**, issue one offer for each, and choose future expiry dates.

## 5 Record student offer decisions

As `s01@demo.edu`, open **Offers** and accept. As `s02@demo.edu`, decline.

Say: “Only the student can accept or decline. Staff can issue or revoke. Acceptance is checked atomically against the one-accepted-offer rule.”

## 6 Demonstrate asynchronous delivery and recovery

Return to the officer account and open **SOA service console**. The outbox contains real records produced by the previous actions.

1. Choose **Simulate outage**.
2. Choose **Process queued events** once. The reporting consumer completes, while notification delivery fails.
3. Process twice more. Failed events move to **DEAD** after three attempts.
4. Open **Placement reports**. Application/offer records and accepted placement are still correct because reporting is an independent consumer.
5. Return to the console and choose **Restore delivery**.
6. Choose **Replay** on one dead event, then process the queue. Its notification completes.
7. Replay that now-delivered event again and process. It creates zero new consumer effects because receipts are retained.

Say: “An outbox row and its business record commit in the same local transaction. Consumers are independently idempotent. We simulate a provider failure here; we do not claim real email delivery or exactly-once transport.”

Requeue the remaining dead events and dispatch if you want all student inbox notifications delivered. One replay button handles one event; it does not replay the entire queue.

## 7 Reproduce the report's calculations

Open **Placement reports** and show source reconciliation:

- Cohort: 6 students.
- Applications: 2.
- Issued offers: 2.
- Distinct students with an accepted offer: 1.
- Offer acceptance proportion: 1 / 2 = 50.0%.
- Accepted-placement proportion: 1 / 6 = 16.7%.

Export CSV. Show that cohort, generation time and counting definitions accompany the numbers. These are actual calculations on fictional local records, not real institutional placement statistics.

## 8 Optional academic correction

As officer, edit S01's academic record after application. Provide a reason and save a new version. Their existing application snapshot remains unchanged. This shows why historical evidence is not overwritten by a corrected current profile. Do this after reproducing the original example, because changing marks can change subsequent eligibility previews.

## Viva answers

**Where is SOA visible?** In the explicit business service modules, API contracts, reusable eligibility operation, coordinator endpoints and event consumers. The service console exposes those boundaries.

**Is this a distributed microservice system?** No. It follows the report's initial modular stage. Independent deployment would need service-owned stores, authenticated network calls, message infrastructure and cross-service consistency controls.

**Why SQLite?** It provides persistent local transactions without a database server. `BEGIN IMMEDIATE` serializes conflicting writes. This suits a classroom demo, not a claim of large-scale throughput.

**Why can reports lag?** Reports use a derived projection updated by consumed events. The UI exposes lag and source reconciliation. A business write does not wait for the consumers.

**How are duplicate submissions prevented?** The idempotency key returns the original result for an identical retry. A separate unique constraint on student/drive prevents two applications with different keys.

**What remains simulated?** Institutional identity and academic imports are replaced by seeded local identities and officer verification. Notification delivery is an in-app provider. There is no live ERP, email, external recruiter system or real university data.

## Screenshot evidence

The `docs/screenshots` folder contains images captured from the running implementation. They illustrate the verified browser run; they are not copied from reference systems. Their fictional data state may differ from your freshly seeded database.
