# State And Artifacts

## 1. StateStore

`StateStore` là nguồn sự thật cho dashboard runtime.

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
- `last_path_repair_at`
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
- `data/last-path-repair-scan.json`

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
- cleanup scan
- path repair scan
- path repair search

Giới hạn:

```text
JOB_LOG_LIMIT = 120
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

Giới hạn:

```text
ACTIVITY_LOG_LIMIT = 200
```

## 6. API payload

`api_payload()` trả:

- state cơ bản
- `report`
- `plan`
- `apply_result`
- `sync_result`
- `cleanup_report`
- `path_repair_report`

Frontend hiện tải phần lớn UI từ payload này cộng với một số endpoint riêng như:

- `/api/process`
- `/api/system/mounts`
- `/api/operations/folders`
- `/api/operations/folders/children`
- `/api/operations/folders/tree`
