---
name: runtime-diagnostics
description: Debug the local media-library-manager runtime by inspecting jobs, ports, reports, state artifacts, and backend health. Use when the dashboard looks stale, API behavior differs from edited files, a job is stuck, a scan keeps timing out, or the backend needs a clean restart.
---

# Runtime Diagnostics

Use this skill to understand what the running app is actually doing before changing code or blaming the UI.

## Workflow

1. Inspect runtime state first.
   Read `/api/process` and `/api/state`.
   Compare live state with files under `data/`.

2. Check ports and processes.
   In this repo, Vite commonly runs on `127.0.0.1:5173` and the Python backend on `127.0.0.1:8766`.
   Confirm which process is actually serving the current API.

3. Inspect logs and artifacts.
   Check `current_job.logs`, `activity_log`, and relevant saved artifacts such as `last-path-repair-scan.json`.

4. Restart cleanly when needed.
   Stop the Python backend, confirm the port is free, then restart with the repo's `PYTHONPATH=src` setup and the correct `data/app-state.json`.

5. Re-verify after restart.
   Confirm that the live API reflects the edited code and current state file before resuming workflow operations.

## Guardrails

- Distinguish between stale saved reports and live provider reality.
- Do not assume Vite and the Python backend restarted together.
- Prefer direct API checks over guessing from the UI.

## Typical Requests

- "Kiểm tra backend đang chạy code nào"
- "Tại sao UI và file state không khớp"
- "Restart backend sạch rồi verify lại"
