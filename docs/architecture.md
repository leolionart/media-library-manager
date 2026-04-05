# Architecture Overview

## 1. Tổng quan

Project hiện gồm 3 lớp chính:

1. React frontend trong [frontend/](/Volumes/DATA/Coding Projects/media-library-manager/frontend)
2. Python backend HTTP server trong `src/media_library_manager`
3. state + artifact files trong `data/`

Backend vừa:

- serve static frontend
- expose API nội bộ
- giữ state của app
- thao tác local filesystem hoặc SMB storage
- nói chuyện với Radarr và Sonarr

## 2. Product shape hiện tại

UI hiện tại có 5 view:

- `Overview`
- `Library Finder`
- `Library Cleanup`
- `Library Path Repair`
- `Settings`

Trọng tâm nghiệp vụ nằm ở ba màn:

- `Library Finder`
- `Library Cleanup`
- `Library Path Repair`

`Overview` là màn tổng hợp số liệu và process state.
`Settings` giữ phần kết nối, roots, và provider setup.

## 3. Module chính

### `web.py`

Là entry point của dashboard server.

Chịu trách nhiệm:

- route static assets
- route API
- scan / plan / apply
- provider APIs
- operations inventory và tree
- cleanup scan
- empty-folder cleanup scan
- path repair scan / search / update / delete
- current job logs và cancel

### `state.py`

Nguồn sự thật của dashboard runtime.

Lưu:

- roots
- integrations
- lan_connections
- activity_log
- current_job
- timestamps
- report / plan / apply / sync artifacts
- cleanup / empty-folder cleanup / path repair artifacts

### `lan_connections.py`

Quản lý SMB profile và thao tác SMB mức connection:

- save / delete profile
- test SMB connection
- browse SMB path
- create / delete SMB directory
- parse output của `smbclient`

### `storage/`

Là storage abstraction mới.

Gồm:

- `paths.py`
- `backends.py`
- `manager.py`

Cho phép code cấp cao làm việc thống nhất với:

- local path
- SMB path

### `scanner_storage.py`

Adapter giữa engine scan và storage abstraction.

Nhờ vậy scan không còn phụ thuộc tuyệt đối vào local mounted path.

### `scanner.py`

Engine scan:

- walk roots
- index video files
- exact duplicate detection
- media collision detection

### `planner.py`

Biến `ScanReport` thành action plan gồm:

- `move`
- `delete`
- `review`

### `operations.py`

Chứa:

- `apply_plan()`
- `move_folder()`
- `move_folder_contents()`
- `delete_folder()`
- `delete_file()`

Hiện hỗ trợ cả local path và SMB path.

### `cleanup_scan.py`

Giữ logic cleanup theo provider library:

- load item từ Radarr / Sonarr
- validate provider path qua local filesystem hoặc connected SMB roots
- scan trực tiếp folder provider đang quản lý
- build `cleanup_report`

### `empty_folder_cleanup.py`

Giữ logic scan các folder trùng tên giữa nhiều roots:

- index folder top-level theo exact name
- inspect đệ quy chỉ với duplicate groups
- gắn cờ `has_video`, `is_deletion_candidate`, `empty_reason`
- build `empty_folder_cleanup_report`

### `path_repair.py`

Giữ logic path repair:

- scan item provider có path lỗi sau bước resolve qua connected roots
- index connected roots
- rank candidate folders theo title/year similarity
- update provider path
- remove provider item

### `sync_integrations.py`

Giữ logic:

- normalize integration config
- test connectivity
- list provider items
- refresh provider item
- sync sau apply

Chỉ các action `move` apply thành công mới đi vào sync.

### `providers/`

Client cho:

- Radarr
- Sonarr

Base client hiện gửi `User-Agent` browser-like để tránh reverse proxy chặn API request.

## 4. Luồng dữ liệu chính

### SMB root setup

`Settings -> /api/lan/connections -> state`

`Settings -> /api/roots hoặc /api/roots/bulk -> state`

### Folder inventory

`roots -> storage manager -> /api/operations/folders`

`roots -> recursive storage walk -> /api/operations/folders/tree`

`tree node expand -> /api/operations/folders/children`

### Scan

`selected folders -> scanner_storage -> scanner.scan_roots() -> last-report.json`

### Plan

`last-report.json -> planner.plan_actions() -> last-plan.json`

### Apply

`last-plan.json -> operations.apply_plan() -> last-apply.json`

Nếu `execute=true`:

`last-plan.json -> apply -> sync_after_apply() -> last-sync.json`

Sau apply execute, backend clear `last-plan.json`.

### Provider move

`Library Finder -> provider items -> move_folder_contents() -> provider refresh`

### Cleanup

`enabled providers -> cleanup_scan.scan_provider_cleanup() -> last-cleanup-scan.json`

`connected roots -> empty_folder_cleanup.scan_duplicate_empty_folders() -> last-empty-folder-cleanup.json`

### Path repair

`enabled providers -> path_repair.scan_provider_path_issues() -> last-path-repair-scan.json`

`selected issue -> path_repair.search_library_paths() -> ranked candidates`

`selected candidate -> path_repair.update_provider_item_path() -> prune saved issue`

`remove action -> path_repair.delete_provider_item() -> prune saved issue`

## 5. Current job model

Các job dài hiện chạy đồng bộ trong request handler nhưng state được cập nhật liên tục.

Mỗi job có:

- `logs`
- `summary`
- `details`
- `cancel_requested`

Frontend chỉ cần poll `GET /api/process`.

Kinds hiện có trong runtime thực tế:

- `scan`
- `plan`
- `apply`
- `cleanup-scan`
- `path-repair`

Cancel hoạt động theo cooperative model:

- `POST /api/process/cancel`
- state ghi `cancel_requested`
- engine dừng ở safe point tiếp theo

UI hiện dùng chung `MediaLibraryLogPanel` để đọc:

- live `current_job.logs`
- filtered `activity_log`

## 6. Nguyên tắc thiết kế hiện tại

### SMB-first cho network storage

Mount local không còn là workflow chính.
SMB roots được truy cập trực tiếp qua `smbclient`.

### Persisted runtime state

Refresh trang không được làm mất `current_job`.
Artifacts mới nhất cũng được giữ lại để overview, cleanup, path repair và logs có thể restore sau refresh.

### Provider là layer bổ trợ

Radarr/Sonarr không điều khiển scan engine.
Chúng chỉ tham gia ở:

- provider item lookup
- provider refresh
- sync sau apply
- cleanup scan
- path repair

### UI mới không dùng mọi state cũ

Backend vẫn còn vài field legacy như `targets` hoặc `managed_folders`, nhưng UI hiện tại không còn dùng chúng.
Chúng nên xem là phần đang chờ dọn tiếp.
