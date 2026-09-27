# Frontend integration contract (proposal for Members 1, 2 and 4)

The backend was not present when this UI was built. These are the request and response shapes the frontend currently expects; align `src/lib/api.ts` with the team's final schema. No provider API keys belong in this frontend.

Set `VITE_API_URL` in `.env` (default `http://localhost:8000`). Allow the Vite origin, usually `http://localhost:5173`, in FastAPI CORS. UI upload limit: 10 MiB, JPEG/PNG/WebP/PDF; enforce the same server-side. Requests time out after 60 seconds.

## POST /explain

Multipart fields: `file` and `language` (`fr` or `ary`). Response:

```json
{
  "document_type": "Ordonnance",
  "summary": "Plain-language explanation in the requested language",
  "items": [{ "title": "Extracted item", "detail": "Explanation" }],
  "next_steps": ["Appropriate next step"],
  "uncertainties": ["Anything unreadable or uncertain"],
  "emergency": { "detected": false, "message": "" },
  "medicines": [
    {
      "name": "Extracted name",
      "instructions": "Instructions from the document",
      "dose": "Exact extracted dose",
      "times": ["08:00"],
      "duration_days": 5
    }
  ]
}
```

`dose`, `times`, and `duration_days` are optional. Omit unknown values instead of fabricating them. The frontend requires the user to fill missing values and confirm the schedule. Use empty arrays for absent sections. Emergency decisions belong to the backend; the frontend displays the flag and message. Lab results can use `items` with an empty `medicines` array.

## POST /chat

JSON: `{ "messages": [{ "role": "user", "content": "..." }], "language": "fr", "context": <explain response or null> }`.

Response: `{ "reply": "...", "emergency": { "detected": false, "message": "" } }`.

## Accuracy report

Member 4 supplies `public/accuracy_report.json`. It is loaded on opening the Accuracy tab and with Refresh. Missing, invalid, and inconsistent reports never display a score.

```json
{
  "total": 1,
  "passed": 1,
  "generated_at": "2026-09-27",
  "cases": [
    {
      "question": "Test question",
      "expected": "Expected behavior",
      "actual": "Observed response",
      "passed": true,
      "category": "emergency"
    }
  ]
}
```

This snippet documents the schema; it is not published as a real evaluation. Counts must agree with the case results. It measures a prototype test set, not clinical validity.
