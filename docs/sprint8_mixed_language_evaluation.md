# Sprint 8 Mixed-Language Evaluation

## Scope

This evaluation is intentionally limited to Sprint 8.

The goal is to verify that the first real LLM layer can:

- understand appointment and availability requests;
- extract date and time information;
- use backend tools;
- handle Lebanese Arabic, Arabizi, English, French, and mixed-language messages.

OpenRouter is used as the model gateway so models can be compared without
changing the surrounding Django pipeline.

## Date context used during testing

- Current local date: 2026-10-08
- Current local weekday: Thursday
- Tenant timezone: Asia/Beirut

The system prompt was refined to include both the current local date and
weekday after weekday-name extraction failures were observed.

## Models tested

### Mistral Small 3.2 24B Instruct

Observed behavior:

- Normal text reply worked.
- Tool calling worked.
- `today` and `tomorrow` were resolved correctly.
- Weekday-name extraction was incorrect in the tested cases.
- Example failure:
  - Friday was resolved as 2026-10-10 instead of 2026-10-09.
  - Thursday was resolved as 2026-10-09 instead of 2026-10-08.

Result: not selected as the current Sprint 8 candidate.

### GPT-4.1 Nano

Observed behavior:

- Tool calling worked.
- `today` and `tomorrow` were resolved correctly.
- The same weekday-name extraction problem was observed.

Result: not selected as the current Sprint 8 candidate.

### Gemini 3.1 Flash Lite

Observed behavior:

- `today` -> 2026-10-08
- `tomorrow` -> 2026-10-09
- `Friday` -> 2026-10-09
- `Thursday` -> 2026-10-08
- Tool calls correctly used `check_availability`.

Mixed-language samples also succeeded for:

- Lebanese Arabic
- Arabizi
- Arabic + English
- French + Arabic
- Arabizi + English

Examples included:

- Arabic: booking tomorrow afternoon
- Arabizi: `bukra ba3ed el dohor`
- English/Arabizi: Friday morning availability
- French/Arabic: rendez-vous tomorrow morning

Result: current Sprint 8 candidate.

## Current limitations

This evaluation is intentionally small and is not a production benchmark.

Audio transcription quality has not yet been evaluated against a real
transcription provider. The Sprint 8 audio pipeline is implemented, but the
provider remains separate from this model comparison.

Production-level observability, large-scale evaluation, advanced guardrails,
cost monitoring, and scalability are outside the Sprint 8 scope.

## Reusable samples

The tested mixed-language examples are stored in:

`integrations/fixtures/mixed_language_samples.json`

They can be reused when comparing future models through OpenRouter.
