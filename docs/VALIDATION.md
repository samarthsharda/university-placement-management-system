# Verification Record

Verified locally on 17 November 2026 using Python 3.12, FastAPI, SQLite and a background Microsoft Edge browser. All datasets were fictional. This record documents executed checks, not projected deployment quality.

## Automated acceptance suite

**16 tests passed.** The suite includes the report's T1–T9 cases, with simultaneous requests coordinated using thread barriers for duplicate submissions, calendar conflicts and competing offer acceptance.

Additional checks cover logout/session revocation, wrong company and student scope, immutable academic snapshots, version conflicts, draft hiding and officer approval, invalid state transitions, expired offers, private PDF access, upload limits, exact 50.0%/16.7% calculations, independent reporting timestamps, current-cohort filtering, and persistence across application instances.

The installed Starlette test client emitted a deprecation warning about its `httpx` adapter; requests and assertions completed successfully. This is a test-tool warning, not an application exception.

## Browser walkthrough

**12 browser scenarios completed; no JavaScript page errors were recorded.**

1. Display the six report-aligned student records.
2. Evaluate the cohort with two eligible students and one review-required record.
3. Submit S01 and S02 applications from the browser and inspect saved evidence.
4. Confirm that the second company sees no first-company applicants.
5. Schedule an interview as the permitted recruiter.
6. Issue offers and record student acceptance and decline.
7. Continue reporting while the notification consumer fails, with 1/6 = 16.7%.
8. Requeue a dead-letter event and recover notification delivery.
9. Render the student overview at 390 px width without horizontal page overflow.
10. Save profile contact details and upload a private PDF version.
11. Create a recruiter draft and approve/close it as the officer.
12. Verify an academic record and restore its original unverified state using new versions.

The launcher was also checked through environment setup and a separate local server start. The API contract in `openapi.json` was generated from the implemented routes.

## Screenshot index

| File | Observed screen |
| --- | --- |
| 01-sign-in.png | Role-based demo sign-in |
| 02-officer-overview.png | Officer dashboard on an initially seeded database |
| 03-student-records.png | Six fictional academic records |
| 04-cohort-eligibility.png | Live eligibility matrix |
| 05-student-eligibility.png | Student preview and submission form |
| 06-submission-evidence.png | Actual persisted decision snapshot |
| 07-interview-schedule.png | Confirmed reservation |
| 08-student-accepted-offer.png | Student's accepted offer |
| 09-service-console-outage.png | Reporting consumer completed while notification events became DEAD |
| 10-placement-report.png | Two applications, two offers, one placed student, 16.7% |
| 11-delivery-recovery.png | A dead event recovered with retained consumer receipts |
| 12-mobile-overview.png | Student overview at a 390 px viewport |

The screenshots were captured from the running implementation, not generated mockups. A new installation starts with no applications; the guide reproduces the observed state. No real email, ERP integration, distributed deployment, load benchmark, backup restoration or formal accessibility certification was verified.
