# State And Artifacts

## 1. StateStore

`StateStore` là nguồn sự thật cho dashboard runtime.

Các mutation của state phải đi qua serialized update trong cùng process.

- không dùng pattern đọc state cũ rồi ghi đè cả file từ snapshot stale
- mỗi lần mutate cần đọc lại state mới nhất dưới lock rồi mới ghi
- mục tiêu là tránh làm rơi `lan_connections`, `roots`, hoặc `current_job` khi nhiều workflow cập nhật state gần nhau

State cơ bản hiện gồm:

- `version`
- `roots`
- `targets`
- `integrations`
- `lan_connections`
- `managed_folders`
- `last_scan_at`
- `last_plan_at`
- `last_apply_at`
- `last_sync_at`
- `last_cleanup_at`
- `last_empty_folder_cleanup_at`
- `last_path_repair_at`
- `last_folder_index_at`
- `activity_log`
- `current_job`

Lưu ý:

- `targets` và `managed_folders` vẫn còn trong backend state
- UI mới hiện không còn dùng chúng

## 2. Artifact files

Nếu state file là:

```text
data/app-state.json
```

thì artifacts là:

- `data/last-report.json`
- `data/last-plan.json`
- `data/last-apply.json`
- `data/last-sync.json`
- `data/last-cleanup-scan.json`
- `data/last-empty-folder-cleanup.json`
- `data/last-path-repair-scan.json`
- `data/last-folder-index.json`

## 3. Current job

`current_job` hiện được persist trong state để refresh không mất tiến trình.

Field chính:

- `id`
- `kind`
- `status`
- `message`
- `summary`
- `details`
- `logs`
- `cancel_requested`
- `started_at`
- `updated_at`
- `finished_at`

## 4. Job logs

Job logs hiện lưu các bước chi tiết của:

- scan
- plan
- apply
- cleanup scan cho duplicate files và empty duplicate folders
- path repair scan
- path repair search
- folder index refresh

Giới hạn:

```text
JOB_LOG_LIMIT = 400
```

## 5. Activity log

Activity log là history cấp cao hơn, dùng để xem event gần đây.

Kinds hiện có thể gồm:

- `config`
- `lan`
- `folder`
- `scan`
- `plan`
- `apply`
- `integration`

`current_job.kind` hiện còn có thể là:

- `cleanup-scan`
- `path-repair`
- `folder-index`

Giới hạn:

```text
ACTIVITY_LOG_LIMIT = 200
```

## 6. API payload

`api_payload()` trả:

- state cơ bản
- `last_empty_folder_cleanup_at`
- `report`
- `plan`
- `apply_result`
- `sync_result`
- `cleanup_report`
- `empty_folder_cleanup_report`
- `path_repair_report`
- `folder_index_summary`

Frontend hiện tải phần lớn UI từ payload này cộng với một số endpoint riêng như:

- `/api/process`
- `/api/system/mounts`
- `/api/operations/folders`
- `/api/operations/folders/children`
- `/api/operations/folders/tree`

Lưu ý cho `path_repair_report`:

- report này hiện phản ánh item `missing` theo chính Radarr/Sonarr
- không dùng report này như nguồn sự thật để suy luận `path_not_found` từ connected roots
- việc tìm folder thay thế đúng vẫn là bước search riêng sau khi user chọn từng issue

Lưu ý cho `last-folder-index.json`:

- đây là metadata cache của thư mục con dưới các connected roots
- artifact này được rebuild từ `Library Finder` refresh
- `Path Repair Search` có thể dùng artifact này để trả candidate nhanh hơn trước khi fallback sang live traversal
