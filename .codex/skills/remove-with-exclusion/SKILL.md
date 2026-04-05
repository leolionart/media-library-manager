---
name: remove-with-exclusion
description: Remove Radarr or Sonarr items without deleting media files and add import exclusion so they are not automatically re-imported. Use when the user wants to remove one provider item, remove a small batch, or verify whether an exclusion was really created.
---

# Remove With Exclusion

Use this skill when removal is intentional and the user wants provider-level exclusion, not filesystem deletion.

## Workflow

1. Confirm the exact provider item first.
   Capture `provider`, `item_id`, and title.

2. Remove with exclusion enabled.
   Use the delete flow with `add_import_exclusion=true`.
   Keep `delete_files=false`.

3. Verify in the right place.
   For Radarr, exclusion lives under `exclusions`, not `blocklist`.
   Explain this difference clearly if the user expects blocklist entries.

4. Recheck provider response and activity log.
   Record whether the provider accepted the delete request and whether exclusion was requested.

## Guardrails

- Do not confuse exclusions with blocklist entries.
- Do not claim an exclusion exists without checking the provider endpoint or recorded response.
- Keep media files on disk unless the user explicitly asks to delete files too.

## Typical Requests

- "Xóa movie khỏi Radarr và chặn auto re-import"
- "Xóa series khỏi Sonarr nhưng giữ media files"
- "Kiểm tra exclusion có thật sự được tạo chưa"
