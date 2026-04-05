---
name: path-repair
description: Investigate Radarr or Sonarr path mismatches and repair only verified old-to-new path changes. Use when the user wants to search for a replacement folder for one provider item, compare old and new paths, or update provider paths after verifying the target folder really exists.
---

# Path Repair

Treat provider data as the source of truth. Do not assume the app's path-repair scan is reliable for rclone-backed libraries unless the provider itself shows a real issue.

## Workflow

1. Start from one specific provider item.
   Capture `provider`, `item_id`, `title`, and `current path`.

2. Search before updating.
   Use the path-repair search flow or direct provider/root inspection to find the real folder.
   Prefer search on one title at a time.

3. Compare old and new explicitly.
   Show `old -> new`.
   Update only when the new path is different and verified.

4. Keep mount namespaces correct.
   For this repo, provider paths must stay in the server namespace such as `/volume2/DATA/rclone/drive/...` or `/volume2/DATA/rclone/gdrive/...`.
   Do not switch provider paths to local pseudo paths that only make sense on the Codex machine.

5. Refresh after update.
   Confirm the provider accepted the new path and queued a refresh.

## Guardrails

- Do not bulk-update same-path rewrites unless the user explicitly asks for that.
- Do not treat the saved path-repair scan as proof of a real provider problem.
- Prefer manual search and verification over auto-mapping for rclone libraries.
- Call out clearly when a "repair" is only a rewrite of the same path.

## Typical Requests

- "Tìm path mới cho một movie Radarr"
- "So sánh old path với new path trước khi update"
- "Search thủ công cho một series Sonarr"
