# Replate Python CLI — Test Plan

**Project:** Replate Python CLI  
**Backend:** Dummy in-memory mock server (replaces `replate-business` Rails API)  
**Date:** 2026-04-18  
**Revision:** 2026-04-18 — Added geo-proximity matching (section 3.5, 4.3 expanded, 5.4 added)

---

## 1. Architecture Under Test

```
replate/
├── client/
│   ├── auth.py            # Login, signup, forgot/reset password
│   ├── onboarding.py      # NPO partner selection
│   ├── available_tasks.py # Browse and claim available pickups
│   ├── my_tasks.py        # In-progress and history views
│   ├── donation.py        # Donation completion (weight, NPO, photo)
│   ├── account.py         # Profile display and logout
│   ├── session.py         # Session persistence (replaces AsyncStorage)
│   └── api.py             # HTTP client (replaces apiUtils.ts)
├── dummy_backend/
│   ├── server.py          # Flask mock server, all API endpoints
│   ├── fixtures.py        # Seed data: drivers, tasks, partners
│   └── store.py           # In-memory state (mutable across requests)
├── tests/
│   ├── conftest.py        # Shared fixtures, client factory, backend setup
│   ├── unit/
│   │   ├── test_auth_validation.py
│   │   ├── test_session.py
│   │   ├── test_api_client.py
│   │   ├── test_task_formatting.py
│   │   └── test_geo.py                 # Haversine + proximity ranking
│   ├── integration/
│   │   ├── test_auth_flows.py
│   │   ├── test_onboarding.py
│   │   ├── test_available_tasks.py
│   │   ├── test_my_tasks.py
│   │   ├── test_donation.py
│   │   └── test_account.py
│   └── e2e/
│       ├── test_new_driver_journey.py
│       └── test_returning_driver_journey.py
└── main.py                # CLI entry point
```

---

## 2. Dummy Backend Specification

The mock server runs as a local Flask app (or `pytest-flask` fixture) and replicates all Rails API endpoints used by the mobile app. It maintains in-memory state that is reset between test runs.

### 2.1 Endpoints to Mock

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/drivers` | Signup — creates a new driver |
| `POST` | `/api/drivers/login` | Login — returns driver object |
| `POST` | `/api/drivers/password` | Request password reset token |
| `PATCH` | `/api/drivers/password` | Submit token + new password |
| `GET` | `/api/drivers/:id` | Fetch driver profile |
| `PATCH` | `/api/drivers/:id` | Update driver (e.g., partner_id) |
| `GET` | `/api/partners` | List all active NPO partners |
| `GET` | `/api/tasks?date=YYYY-MM-DD[&lat=&lon=]` | Available tasks, optionally sorted by proximity |
| `GET` | `/api/tasks/:encrypted_id` | Fetch full task detail |
| `POST` | `/api/tasks/:encrypted_id/claim` | Claim a task for the current driver |
| `GET` | `/api/my_tasks` | List tasks assigned to the current driver |
| `PATCH` | `/api/tasks/:id/update_completion_details` | Submit donation completion |

### 2.2 Seed Data

```python
# fixtures.py
PARTNERS = [
    {"id": 1, "name": "SF-Marin Food Bank"},
    {"id": 2, "name": "Glide Memorial Kitchen"},
    {"id": 3, "name": "St. Anthony Foundation"},
]

TASKS = [
    {
        "id": 101, "encrypted_id": "enc_abc123",
        "date": "2026-04-18",
        "start_time": "10:00", "end_time": "11:00",
        "donor_name": "Google Cafeteria",
        "address": {"street": "1600 Amphitheatre Pkwy", "city": "Mountain View", "state": "CA", "zip": "94043"},
        "lat": 37.4220, "lon": -122.0841,   # Mountain View — ~48 km from Alice
        "contact_name": "Jane Smith", "contact_phone": "6505550100", "contact_email": "jane@google.com",
        "food_description": "Mixed entrees", "tray_type": "full", "tray_count": 8,
        "access_instructions": "Check in at lobby reception",
        "status": "available", "driver_id": None,
    },
    {
        "id": 102, "encrypted_id": "enc_def456",
        "date": "2026-04-18",
        "start_time": "14:00", "end_time": "15:30",
        "donor_name": "LinkedIn Café",
        "address": {"street": "222 2nd St", "city": "San Francisco", "state": "CA", "zip": "94105"},
        "lat": 37.7877, "lon": -122.3974,   # SoMa SF — ~2.4 km from Alice
        "contact_name": "Bob Lee", "contact_phone": "4155550199", "contact_email": "bob@linkedin.com",
        "food_description": "Salads and sandwiches", "tray_type": "half", "tray_count": 12,
        "access_instructions": "Side entrance on Minna St",
        "status": "available", "driver_id": None,
    },
    {
        "id": 103, "encrypted_id": "enc_ghi789",
        "date": "2026-04-19",
        "start_time": "09:00", "end_time": "10:00",
        "donor_name": "Salesforce Tower Café",
        "address": {"street": "415 Mission St", "city": "San Francisco", "state": "CA", "zip": "94105"},
        "lat": 37.7895, "lon": -122.3963,   # Financial District SF — ~2.6 km from Alice
        "contact_name": "Maria Chen", "contact_phone": "4155550200", "contact_email": "maria@sf.com",
        "food_description": "Hot meals", "tray_type": "full", "tray_count": 6,
        "access_instructions": "", "status": "available", "driver_id": None,
    },
]

DRIVERS = [
    {
        "id": 1, "email": "alice@example.com", "password_hash": bcrypt("password123A"),
        "first_name": "Alice", "last_name": "Driver",
        "phone": "4155550001", "partner_id": 1,
        "lat": 37.7749, "lon": -122.4194,   # SF downtown
    },
]
```

### 2.3 Error Responses

The mock server must return realistic error shapes for all failure paths:

```json
{ "error": "Invalid email or password" }           // 401
{ "errors": ["Email has already been taken"] }     // 422
{ "error": "Task already claimed" }                // 409
{ "error": "Unauthorized" }                        // 401 (no session)
{ "error": "Not found" }                           // 404
```

---

## 3. Unit Tests

### 3.1 Input Validation (`test_auth_validation.py`)

Tests for `auth.py`'s client-side validation logic, mirroring `validation.ts` from the original app.

| Test ID | Input | Expected |
|---------|-------|----------|
| `VAL-001` | Email `"alice@example.com"` | Valid |
| `VAL-002` | Email `"not-an-email"` | Error: invalid email format |
| `VAL-003` | Email `""` | Error: email required |
| `VAL-004` | Email 255 chars | Error: max 254 chars |
| `VAL-005` | Password `"Password1"` | Valid |
| `VAL-006` | Password `"short"` | Error: min 8 chars |
| `VAL-007` | Password `"alllowercase1"` | Error: requires uppercase letter |
| `VAL-008` | Password `""` | Error: password required |
| `VAL-009` | Password 129 chars | Error: max 128 chars |
| `VAL-010` | Phone `"4155550001"` | Valid (10 digits) |
| `VAL-011` | Phone `"415555000"` | Error: min 10 digits |
| `VAL-012` | Phone `"4155550001234567"` | Error: max 15 digits |
| `VAL-013` | Phone `"415-555-0001"` | Behavior defined: strip non-digits or error |
| `VAL-014` | First name `"Alice"` | Valid |
| `VAL-015` | First name `""` | Error: required |
| `VAL-016` | First name 51 chars | Error: max 50 chars |
| `VAL-017` | Password confirm mismatch | Error: passwords do not match |

### 3.2 Session Persistence (`test_session.py`)

Tests for `session.py`, which replaces `AsyncStorage` with a local JSON file or in-memory dict.

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `SES-001` | Save driver object and reload | Reloaded object equals original |
| `SES-002` | No session file exists | Returns `None` |
| `SES-003` | Corrupt session file (invalid JSON) | Returns `None`, no crash |
| `SES-004` | Clear session | Subsequent load returns `None` |
| `SES-005` | Session contains all required fields | `id`, `email`, `first_name`, `last_name`, `phone`, `partner_id` present |

### 3.3 API Client (`test_api_client.py`)

Tests for `api.py`'s request wrapper, independent of business logic.

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `API-001` | Successful `GET` returns parsed JSON | Response dict returned |
| `API-002` | Server returns 401 | Raises `AuthError` |
| `API-003` | Server returns 404 | Raises `NotFoundError` |
| `API-004` | Server returns 409 | Raises `ConflictError` |
| `API-005` | Server returns 422 with `errors[]` | Raises `ValidationError` with `errors` list |
| `API-006` | Server returns 204 No Content | Returns `None` without raising |
| `API-007` | Request times out (30s default) | Raises `TimeoutError` |
| `API-008` | Connection refused (server down) | Raises `ConnectionError` with friendly message |
| `API-009` | Response contains prototype-pollution payload `{"__proto__": {"admin": true}}` | Sanitized — no prototype pollution |
| `API-010` | Invalid JSON response body | Raises `ApiError` |

### 3.4 Task Formatting (`test_task_formatting.py`)

Tests for display formatting helpers in `available_tasks.py` and `my_tasks.py`.

| Test ID | Input | Expected |
|---------|-------|----------|
| `FMT-001` | `start_time="14:00"`, `end_time="15:30"` | `"2:00 PM – 3:30 PM"` |
| `FMT-002` | `start_time=None` | `"Time TBD"` |
| `FMT-003` | Address with all fields | `"1600 Amphitheatre Pkwy, Mountain View, CA 94043"` |
| `FMT-004` | Address missing zip | `"222 2nd St, San Francisco, CA"` |
| `FMT-005` | Date `"2026-04-18"` | `"Saturday, April 18"` |
| `FMT-006` | `tray_count=8`, `tray_type="full"` | `"8 full trays"` |
| `FMT-007` | `distance_km=None` | `""` (empty string) |
| `FMT-008` | `distance_km=0.3` | `"300 m"` |
| `FMT-009` | `distance_km=1.5` | `"1.5 km"` |
| `FMT-010` | `distance_km=48.3` | `"48.3 km"` |
| `FMT-011` | `distance_km=0.0` | `"0 m"` |

### 3.5 Geo-Proximity (`test_geo.py`)

Tests for the Haversine distance formula in `dummy_backend/server.py` and proximity-based ranking logic.

**Reference coordinates used throughout:**

| Location | lat | lon | Role |
|---|---|---|---|
| SF downtown (Alice) | 37.7749 | -122.4194 | Driver home base |
| LinkedIn Café (SoMa SF) | 37.7877 | -122.3974 | ~2.4 km from Alice |
| Salesforce Tower (FiDi SF) | 37.7895 | -122.3963 | ~2.6 km from Alice |
| Google Cafeteria (Mtn View) | 37.4220 | -122.0841 | ~48 km from Alice |

**Haversine correctness**

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `GEO-001` | Same point → same point | `0.0` km |
| `GEO-002` | SF → Mountain View | Between 45 and 52 km |
| `GEO-003` | SF → LinkedIn Café | < 5 km |
| `GEO-004` | SF → Salesforce Tower | < 5 km |
| `GEO-005` | SF → NYC | Between 4000 and 4200 km |
| `GEO-006` | A→B distance equals B→A distance (symmetry) | Difference < 0.001 km |
| `GEO-007` | Triangle inequality holds for SF / LinkedIn / Salesforce | `d(A,B) + d(B,C) >= d(A,C)` |

**Proximity ranking**

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `GEO-010` | From SF: LinkedIn vs Google | LinkedIn distance < Google distance |
| `GEO-011` | From SF: LinkedIn vs Salesforce | LinkedIn distance < Salesforce distance |
| `GEO-012` | From SF: Google is farthest of the three | Google distance = max of all three |
| `GEO-013` | From Mountain View: Google is nearest | Google distance = min; effectively 0 km |

---

## 4. Integration Tests

### 4.1 Authentication Flows (`test_auth_flows.py`)

All tests run against the dummy backend.

**Login**

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `AUTH-001` | Valid credentials | Returns driver object; session saved |
| `AUTH-002` | Wrong password | `AuthError` raised; session not saved |
| `AUTH-003` | Unregistered email | `AuthError` raised |
| `AUTH-004` | Empty email | Client-side `ValidationError` before network call |
| `AUTH-005` | Empty password | Client-side `ValidationError` before network call |
| `AUTH-006` | "Stay signed in" = True | Session file written to disk |
| `AUTH-007` | "Stay signed in" = False | Session file not written |

**Signup**

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `AUTH-010` | All valid fields, new email | Driver created; session optionally saved |
| `AUTH-011` | Email already registered | `ValidationError` with "Email has already been taken" |
| `AUTH-012` | Password fails validation | Client-side error; no network call made |
| `AUTH-013` | Phone fails validation | Client-side error; no network call made |
| `AUTH-014` | New driver has `partner_id = None` | After signup, routed to onboarding |

**Password Reset**

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `AUTH-020` | Request reset for known email | Success message; backend stores reset token |
| `AUTH-021` | Request reset for unknown email | Server returns 404; error shown |
| `AUTH-022` | Submit valid token + new password | Password updated; can login with new password |
| `AUTH-023` | Submit invalid token | Server returns 422; error shown |
| `AUTH-024` | Submit expired token | Server returns 422; error shown |
| `AUTH-025` | New password fails validation | Client-side error; no network call |

**Logout**

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `AUTH-030` | Logout while authenticated | Session cleared; subsequent calls require re-login |
| `AUTH-031` | Logout with no session | No error; clean state |

### 4.2 Onboarding (`test_onboarding.py`)

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `ONB-001` | New driver with `partner_id = None` | Routed to onboarding before main app |
| `ONB-002` | Fetch partner list | Returns 3 partners from seed data |
| `ONB-003` | Select a valid partner | `PATCH /api/drivers/:id` called with `partner_id`; profile updated |
| `ONB-004` | Select no partner and proceed | Error shown; onboarding not completed |
| `ONB-005` | Returning driver with `partner_id` set | Onboarding skipped; routed to main app |
| `ONB-006` | API returns empty partner list | User shown "no partners available" message |
| `ONB-007` | Filter partners by search term | Only matching names shown (client-side filter) |

### 4.3 Available Pick-ups (`test_available_tasks.py`)

**Basic listing**

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `AVAIL-001` | Fetch tasks for today (2026-04-18) | Returns tasks 101, 102 (not 103) |
| `AVAIL-002` | Fetch tasks for tomorrow (2026-04-19) | Returns task 103 only |
| `AVAIL-003` | Fetch tasks for date with no pickups | Empty list; "no pickups available" message |
| `AVAIL-004` | All tasks for date already claimed | Empty list (claimed tasks excluded) |
| `AVAIL-005` | Display task card | Time window, donor name, and location shown |
| `AVAIL-006` | View pickup details | Full task details displayed (address, contact, food, access) |
| `AVAIL-007` | Task has no access instructions | Field omitted or shown as blank |
| `AVAIL-008` | API error on fetch | Error message shown; app does not crash |

**Geo-proximity — `distance_km` field**

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `AVAIL-010` | Request with `lat`/`lon` | Every task in response has `distance_km` float ≥ 0 |
| `AVAIL-011` | Request without `lat`/`lon` | No task has `distance_km` field |
| `AVAIL-012` | Request with only `lat` (missing `lon`) | No proximity sorting; no `distance_km` |
| `AVAIL-013` | SF driver → LinkedIn Café | `distance_km` < 5 |
| `AVAIL-014` | SF driver → Google Cafeteria | `distance_km` > 40 |
| `AVAIL-015` | SF driver → Salesforce Tower (tomorrow) | `distance_km` < 5 |

**Geo-proximity — sort order**

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `AVAIL-020` | SF driver fetches today's tasks | LinkedIn Café (2.4 km) appears before Google Cafeteria (48 km) |
| `AVAIL-021` | Mountain View driver fetches today's tasks | Google Cafeteria appears before LinkedIn Café |
| `AVAIL-022` | `distance_km` values are non-decreasing in response | Ascending sort confirmed |
| `AVAIL-023` | Two requests with different locations return different orderings | Order is not cached between calls |

**Geo-proximity — store immutability**

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `AVAIL-030` | Call with location then call without location | Second response has no `distance_km` |
| `AVAIL-031` | Call with SF location then call with Mtn View location | Second response sorted from Mtn View perspective |

**Driver location on profile**

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `AVAIL-040` | PATCH driver with `lat`/`lon` | Profile stores coordinates |
| `AVAIL-041` | Driver with `lat`/`lon` = null fetches tasks | Tasks returned without `distance_km` (graceful fallback) |

### 4.4 Claim a Pickup

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `CLAIM-001` | Claim an available task | `POST /api/tasks/:encrypted_id/claim` called; task assigned to driver |
| `CLAIM-002` | Task appears in My Tasks after claim | `GET /api/my_tasks` returns the claimed task |
| `CLAIM-003` | Task no longer in available list after claim | `GET /api/tasks?date=...` excludes the claimed task |
| `CLAIM-004` | Claim a task already claimed by another driver | `ConflictError` (409) raised; user notified |
| `CLAIM-005` | Claim task while unauthenticated | `AuthError` (401) raised; user redirected to login |
| `CLAIM-006` | Invalid encrypted_id | `NotFoundError` (404) raised |

### 4.5 My Tasks (`test_my_tasks.py`)

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `TASKS-001` | Driver with one claimed task | Task shown in "In Progress" view |
| `TASKS-002` | Driver with no tasks | "No tasks" message shown |
| `TASKS-003` | Completed task shown in History | Task appears in "History" view, not "In Progress" |
| `TASKS-004` | In Progress and History are mutually exclusive | A task does not appear in both views |
| `TASKS-005` | Task card shows date, time, location | All three fields present in display |
| `TASKS-006` | Multiple tasks sorted by date | Most recent date first |
| `TASKS-007` | Unauthenticated access | `AuthError` raised |

### 4.6 Donation Completion (`test_donation.py`)

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `DON-001` | Submit valid weight (45.5), NPO, no photo | `PATCH /api/tasks/:id/update_completion_details` called; task marked complete |
| `DON-002` | Submit with photo path | Photo uploaded to (mock) Supabase storage; URL included in PATCH payload |
| `DON-003` | Mark task as missed | Task updated to missed status |
| `DON-004` | Weight is empty | Error: weight required |
| `DON-005` | Weight is non-numeric (e.g., "forty") | Error: must be a number |
| `DON-006` | Weight is negative | Error: must be positive |
| `DON-007` | Weight is zero | Error or warning: must be > 0 |
| `DON-008` | No NPO selected | Error: NPO required |
| `DON-009` | Photo path does not exist | Error: file not found |
| `DON-010` | Photo MIME type not image | Error: unsupported file type |
| `DON-011` | Complete task that is already completed | `ConflictError` or appropriate error |
| `DON-012` | NPO dropdown populated from `GET /api/partners` | Live partner list shown (not hardcoded) |
| `DON-013` | Completed task moves to History view | After completion, task appears in My Tasks History |

### 4.7 Account (`test_account.py`)

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `ACCT-001` | View profile while authenticated | First name, last name, email, phone, NPO name shown |
| `ACCT-002` | NPO name resolved from partner list | `partner_id` matched to partner name string |
| `ACCT-003` | Driver has no partner_id | NPO field shows "None" or "Not set" |
| `ACCT-004` | Logout | Session cleared; next action requires login |
| `ACCT-005` | View profile with stale session | If backend returns 401, user redirected to login |

---

## 5. End-to-End Flows

### 5.1 New Driver Journey (`test_new_driver_journey.py`)

Full flow for a first-time user, run against the dummy backend in a fresh state.

```
1. Start CLI — no session file exists
2. Signup: valid new email, valid password, phone, name
   └─ Assert: driver created in dummy backend
3. Routed to onboarding
4. Fetch partner list — assert 3 partners shown
5. Select "SF-Marin Food Bank" (id=1)
   └─ Assert: PATCH /api/drivers/:id called with partner_id=1
6. Routed to main app (Available Pick-ups)
7. Browse today's tasks — assert tasks 101, 102 shown
8. Select task 101 (enc_abc123) — view full details
   └─ Assert: all fields displayed (donor, address, contact, food, access)
9. Claim task 101
   └─ Assert: task 101 removed from available list
   └─ Assert: task 101 appears in My Tasks > In Progress
10. View My Tasks — assert task 101 shown
11. Complete task 101: weight=42.5, NPO=1, no photo
    └─ Assert: PATCH called with correct payload
    └─ Assert: task 101 moves to My Tasks > History
12. View Account — assert name, email, phone, NPO name correct
13. Logout — assert session cleared
14. Attempt to view available tasks — assert redirected to login
```

### 5.2 Returning Driver Journey (`test_returning_driver_journey.py`)

Flow for a driver with a pre-existing session.

```
1. Pre-seed: session file with valid driver (id=1, partner_id=1)
2. Start CLI — session loaded automatically
3. Routed directly to Available Pick-ups (onboarding skipped)
4. Switch to "Tomorrow" date — assert task 103 shown
5. View task 103 details
6. Claim task 103
7. Navigate to My Tasks — assert task 103 in In Progress
8. Mark task 103 as missed
   └─ Assert: task 103 status = missed
   └─ Assert: task 103 appears in History (not In Progress)
9. Request password reset for registered email
   └─ Assert: reset token stored in dummy backend
10. Submit valid reset token + new password
    └─ Assert: login with old password fails
    └─ Assert: login with new password succeeds
```

### 5.3 Geo-Proximity End-to-End (`test_geo_journey.py`)

```
Scenario A — SF driver sees nearest tasks first
1. Login as Alice (lat=37.7749, lon=-122.4194, SF downtown)
2. Fetch today's available tasks with Alice's location
   └─ Assert: LinkedIn Café is first in list (distance_km < 5)
   └─ Assert: Google Cafeteria is last (distance_km > 40)
   └─ Assert: distance_km values are non-decreasing
3. Claim LinkedIn Café (nearest)
4. Fetch available tasks again
   └─ Assert: only Google Cafeteria remains
   └─ Assert: distance_km still present and > 40

Scenario B — Mountain View driver sees different ordering
1. Create new driver with Mountain View location (lat=37.4220, lon=-122.0841)
2. Fetch today's tasks with that location
   └─ Assert: Google Cafeteria is first (distance_km < 1)
   └─ Assert: LinkedIn Café is second (distance_km > 40)

Scenario C — Driver with no location set gets unsorted list
1. Create driver, do not set lat/lon
2. Fetch tasks without lat/lon params
   └─ Assert: tasks returned (2 for today)
   └─ Assert: no distance_km field on any task
```

### 5.4 Concurrent Claim Race Condition (`test_concurrent_claim.py`)

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `RACE-001` | Two drivers attempt to claim the same task simultaneously | First claim succeeds (200); second returns 409 Conflict |
| `RACE-002` | Task claimed by driver A is not visible to driver B in available list | Driver B's `GET /api/tasks` excludes the claimed task |

---

## 6. Error Handling and Edge Cases

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `ERR-001` | Backend unreachable (server not started) | Friendly "cannot connect to server" message; no traceback |
| `ERR-002` | Backend returns 500 | Friendly "server error" message; app does not crash |
| `ERR-003` | Malformed JSON response | `ApiError` raised with safe message |
| `ERR-004` | Session file exists but driver ID no longer valid | 404 on profile fetch; session cleared; routed to login |
| `ERR-005` | Keyboard interrupt during input prompt | Clean exit; no partial data written |
| `ERR-006` | Empty task list on Available Pick-ups | "No pick-ups available for this date" message |
| `ERR-007` | Partner list empty | "No NPO partners available" shown in onboarding and donation form |
| `ERR-008` | Task `encrypted_id` collision in seed data | Raises on fixture load (data integrity check) |

---

## 7. Security Tests

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `SEC-001` | Prototype pollution in API response `{"__proto__": {"isAdmin": true}}` | Sanitized; `isAdmin` not accessible on object prototype |
| `SEC-002` | Login response contains extra fields beyond spec | Extra fields ignored; no crash |
| `SEC-003` | Session file manually edited with different `driver_id` | App accepts stored data (consistent with AsyncStorage model); note for future: add HMAC |
| `SEC-004` | SQL injection string as email (e.g., `"' OR 1=1 --"`) | Client-side validation rejects as invalid email |
| `SEC-005` | Oversized payload (password > 128 chars) | Client-side validation rejects before network call |
| `SEC-006` | Claim task belonging to another driver | Backend returns 403 or 409; error shown |

---

## 8. Dummy Backend Behavioral Tests

Tests that verify the mock server itself behaves correctly (so integration tests can trust it).

| Test ID | Scenario | Expected |
|---------|----------|----------|
| `MOCK-001` | State reset between test runs | Fresh seed data every test; no cross-test contamination |
| `MOCK-002` | Login increments no state | GET /drivers/:id returns same data after login |
| `MOCK-003` | Claim task mutates state | Task status changes to "claimed"; `driver_id` populated |
| `MOCK-004` | Complete task mutates state | Task `completion_details` populated; status = "completed" |
| `MOCK-005` | Mark task missed mutates state | Task status = "missed" |
| `MOCK-006` | Reset token is single-use | Second `PATCH /api/drivers/password` with same token returns 422 |
| `MOCK-007` | Password hash check on login | Plaintext comparison or bcrypt depending on implementation |
| `MOCK-008` | `GET /api/tasks?date=` filters by exact date | Only tasks for that date returned |

---

## 9. Test Infrastructure

### 9.1 Dependencies

```
pytest
pytest-flask          # Spin up dummy Flask backend as fixture
responses             # Optional: mock HTTP at requests level for unit tests
freezegun             # Freeze datetime for date-sensitive tests
```

### 9.2 Fixtures (`conftest.py`)

```python
@pytest.fixture(scope="function")
def backend(app):
    """Start dummy backend; reset in-memory store before each test."""
    store.reset()
    return app.test_client()

@pytest.fixture
def auth_client(backend):
    """API client pre-authenticated as Alice (driver id=1)."""
    # POST /api/drivers/login → seed Alice's credentials
    ...

@pytest.fixture
def new_driver_client(backend):
    """API client with no session (simulates first-time user)."""
    ...
```

### 9.3 Running the Tests

```bash
# All tests
pytest tests/

# Unit only
pytest tests/unit/

# Integration only
pytest tests/integration/

# E2E only
pytest tests/e2e/

# Single test file
pytest tests/integration/test_auth_flows.py -v

# With coverage
pytest tests/ --cov=client --cov-report=term-missing
```

### 9.4 Coverage Targets

| Module | Target |
|--------|--------|
| `auth.py` | 95% |
| `api.py` | 90% |
| `session.py` | 100% |
| `available_tasks.py` | 85% |
| `my_tasks.py` | 85% |
| `donation.py` | 90% |
| `account.py` | 80% |
| `dummy_backend/` | 80% |

---

## 10. Out of Scope

- **Photo upload to real Supabase:** Tests use a local file path and a mock upload endpoint that stores a URL string.
- **Deep links (tel:, maps):** The CLI has no concept of these; phone/address are displayed as plain text.
- **Push notifications:** Not in scope for v1.
- **Multi-driver concurrency stress test:** Race condition tests (section 5.3) cover the behavioral contract; load testing is out of scope.
- **Real Rails backend compatibility:** The dummy backend is not validated against the actual `replate-business` Rails API schema — this is a separate integration concern.
