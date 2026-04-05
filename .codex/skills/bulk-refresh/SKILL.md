---
name: bulk-refresh
description: Run controlled bulk provider path rewrites and refreshes with batching, progress checks, and failure tracking. Use when the user explicitly wants to rewrite many Radarr or Sonarr items with known paths, rerun provider refreshes in bulk, or measure whether same-path rewrites change provider behavior.
---

# Bulk Refresh

Use this skill only when the user explicitly wants bulk behavior. This workflow can touch hundreds of provider items and should be treated as operational work, not diagnosis.

## Workflow

1. Check the runtime first.
   Ensure no conflicting scan, search, or cleanup job is already running.

2. Define the exact batch.
   Capture the provider, item ids, and path source.
   State clearly whether this is a real path change or a same-path rewrite.

3. Apply in controlled chunks.
   Prefer batches of about 20 items with a short pause between chunks.
   Track cumulative success and failure counts.

4. Stop on meaningful error signals.
   Stop when there are repeated HTTP 4xx or provider timeouts that suggest the batch definition is wrong.
   Continue through isolated missing-item cases when the user explicitly wants best-effort processing.

5. Persist a summary.
   Save a machine-readable success/failure summary when the batch is large.
   Report the final `success`, `failed`, and representative failures.

## Guardrails

- Do not start bulk refresh while another provider job is running.
- Call out clearly when the user is asking for same-path rewrites rather than real path changes.
- Use provider item ids directly when possible; do not list the entire provider library just to update one item.

## Typical Requests

- "Refresh toàn bộ path Radarr còn lại"
- "Batch update Sonarr issues theo best effort"
- "Theo dõi success/fail của một bulk rewrite lớn"
