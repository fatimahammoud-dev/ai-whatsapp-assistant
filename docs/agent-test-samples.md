# Sprint 9 — Ticket 3: Availability Pagination and Localized Replies

## Scope

This ticket improves the booking assistant's availability responses.

Implemented behavior:

- Offer at most three available appointment slots.
- Sort available slots chronologically.
- Track the last offered date.
- Support requesting additional options.
- Continue searching forward after an empty availability window.
- Allow an explicit requested date to override pagination.
- Clear previously offered slots when availability is empty.
- Prevent booking flows from relying on stale offered slots.
- Use OpenRouter to select a localized introductory reply.
- Append verified appointment times using backend data.
- Reject unapproved AI-generated appointment text.
- Fall back to a backend-generated reply if formatting fails.

## Safety Decision

The model is not trusted to generate appointment dates or times.

For availability replies, only approved introductory phrases
are accepted from the formatter.

The backend appends appointment slots obtained from the
calendar availability tool.

Unapproved AI-generated text is discarded.

This reduces the risk of invented appointment times, but
limits the natural variation of responses.

## Pagination Behavior

The assistant offers a maximum of three earliest slots.

When the customer rejects the offered options, the assistant
can search a subsequent date range.

The search cursor is tracked separately from the last
offered date so an empty search does not cause the assistant
to repeat the previous search window.

An explicit date request takes precedence over pagination.

## Localization

The formatter receives conversation context and the latest
buffered customer messages.

Approved introductions include English, Arabic, and French.

The appointment date/time list is rendered by the backend
in a fixed numeric format.

The mocked tests do not establish the quality of responses
from a live OpenRouter model.

## Test Scenarios

### Scenario 1 — Three available slots

Given more than three available slots:

Expected:
- Return no more than three.
- Offer the earliest slots first.
- Store only the offered slots.

### Scenario 2 — Customer rejects offered slots

Customer: "Do you have other options?"

Expected:
- Search after the last offered date.
- Avoid repeating the previous search range.

### Scenario 3 — Repeated rejection with empty availability

Customer requests more options repeatedly.

Expected:
- Advance the search cursor.
- Do not restart the previous empty window.
- Keep offered_slots empty.

### Scenario 4 — Explicit date override

Customer: "What about November 5?"

Expected:
- Search the explicitly requested date.
- Do not use the previous pagination range.

### Scenario 5 — Arabic customer

Customer: "بدي موعد عند الدكتور"

Expected:
- Formatter receives the Arabic customer message.
- Arabic is supported among approved introductory replies.
- Backend remains responsible for appointment times.

### Scenario 6 — French customer

Customer: "Je voudrais un rendez-vous"

Expected:
- Formatter receives the French customer message.
- French is supported among approved introductory replies.
- Backend remains responsible for appointment times.

### Scenario 7 — Invented appointment

Formatter returns:
"Tomorrow afternoon is also available."

Expected:
- Discard the unapproved text.
- Send only the backend-generated verified availability.

### Scenario 8 — Formatter failure

Formatter raises an exception.

Expected:
- Use the backend fallback.
- Preserve verified appointment information.

### Scenario 9 — No availability

The calendar returns no slots.

Expected:
- Do not offer old slots.
- Clear last_offered_date.
- Preserve forward-search progress where applicable.

## Automated Tests

Relevant test modules:

- integrations/test_ticket3_pagination.py
- integrations/test_ticket3_backend_pagination.py
- integrations/test_ticket3_localization.py
- integrations/test_ticket3_safety.py
- integrations/test_multi_turn_booking.py
- integrations/test_openrouter_agent.py
- integrations/test_create_booking.py

## Limitations and Follow-up

- Live Arabic/French OpenRouter behavior has not been verified
  by these mocked tests.
- Responses use fixed-format appointment dates and times,
  not fully localized date formatting.
- The approved-introduction approach prioritizes safety
  over flexible natural-language variation.
- A live end-to-end WhatsApp and calendar test remains
  separate from mocked verification.
- Do not enable paid API usage without Issa's approval.

## Status

Implementation is ready for final local verification.

No commit, push, or merge is performed by this document.
