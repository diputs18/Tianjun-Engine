# Dashboard Test Checklist

The Dashboard is static HTML/CSS/JS and has no build step. Before demos, run the smoke test and then verify the following manually:

- `/dashboard` loads without browser console errors.
- Top navigation shows system status from `/health`.
- Overview page renders metrics from `/report`.
- Topology page shows an empty state when no nodes are registered.
- Scheduling chat sends messages through `/chat/sessions/stream`.
- The final submit button commits through `/chat/sessions/{session_id}/commit`.
- Model page weight updates require explicit confirmation and call `/policy-weights`.
- Task cancellation calls `/task-runs/cancel`.
- No Dashboard code calls `/intent`, `/chat`, or `/hermes/*`.
