---
name: duplicate-cleanup
description: Clean duplicate movie or series folders on connected rclone or SMB roots. Use when the user wants to scan for duplicate folders, review deletion candidates, rerun cleanup on a narrow scope such as drive/gdrive Movies or TV Series, or apply duplicate-folder deletions in safe batches.
---

# Duplicate Cleanup

Inspect the current saved report first, then rerun the narrowest cleanup scan that matches the user's target roots. Prefer scoped scans on the exact movie or series roots instead of broad full-library scans.

## Workflow

1. Check runtime state before scanning.
   Read `/api/process` and `/api/state`.
   Confirm no long-running job is active before starting a cleanup workflow.

2. Use the narrowest scan scope possible.
   For movie cleanup on rclone, prefer only the exact `drive/Movies` and `gdrive/Movies` roots.
   For TV cleanup, prefer only the exact `Series`, `TV Series`, or `Animated` roots the user mentions.

3. Review deletion candidates before applying.
   Treat the scan report as a candidate list, not as permission to delete everything blindly.
   Prefer batching deletions and rechecking after each batch.

4. Apply in batches.
   Prefer small batches when the cleanup touches provider-managed media.
   Stop when the backend reports repeated storage or provider errors.

5. Verify after apply.
   Re-read `/api/state` and the relevant saved report.
   Confirm the target duplicate groups or deletion candidates actually went down.

## Guardrails

- Do not trust stale reports blindly. Re-run a scoped scan when the user is about to delete.
- Do not mix cleanup apply with unrelated path-repair or provider jobs.
- Prefer exact movie or series roots over mixed roots when the user already knows the target area.
- Summarize the exact roots scanned, the number of groups found, and what was deleted.

## Typical Requests

- "Quét lại duplicate folder cho Movies trên drive và gdrive"
- "Xóa batch duplicate movie folders an toàn"
- "Kiểm tra TV series có còn trùng không"
