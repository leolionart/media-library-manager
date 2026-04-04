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

UI hiện tại có 3 view:

- `Overview`
- `Operations`
- `Settings`

Trọng tâm nghiệp vụ nằm ở `Operations`.
`Settings` chỉ giữ phần kết nối và provider setup.

## 3. Module chính

### `web.py`

Là entry point của dashboard server.

Chịu trách nhiệm:

- route static assets
- route API
- scan / plan / apply
- provider APIs
- operations inventory và tree
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

Hiện hỗ trợ cả local path và SMB path.

### `providers/`

Client cho:

- Radarr
- Sonarr

Base client hiện gửi `User-Agent` browser-like để tránh reverse proxy chặn API request.

### `sync_integrations.py`

Giữ logic:

- normalize integration config
- test connectivity
- list provider items
- refresh provider item
- sync sau apply

## 4. Luồng dữ liệu chính

### SMB root setup

`Settings -> /api/lan/connections -> state`

`Settings -> /api/roots hoặc /api/roots/bulk -> state`

### Folder inventory

`roots -> storage manager -> /api/operations/folders`

`roots -> recursive storage walk -> /api/operations/folders/tree`

### Scan

`roots -> scanner_storage -> scanner.scan_roots() -> last-report.json`

### Plan

`last-report.json -> planner.plan_actions() -> last-plan.json`

### Apply

`last-plan.json -> operations.apply_plan() -> last-apply.json`

### Provider move

`Operations -> provider items -> move_folder_contents() -> provider refresh`

### Sync

`plan + apply_result + integrations -> sync_after_apply() -> last-sync.json`

## 5. Current job model

Các job dài hiện chạy đồng bộ trong request handler nhưng state được cập nhật liên tục.

Mỗi job có:

- `logs`
- `summary`
- `details`
- `cancel_requested`

Frontend chỉ cần poll `GET /api/process`.

Cancel hoạt động theo cooperative model:

- `POST /api/process/cancel`
- state ghi `cancel_requested`
- engine dừng ở safe point tiếp theo

## 6. Nguyên tắc thiết kế hiện tại

### SMB-first cho network storage

Mount local không còn là workflow chính.
SMB roots được truy cập trực tiếp qua `smbclient`.

### Persisted runtime state

Refresh trang không được làm mất `current_job`.

### Provider là layer bổ trợ

Radarr/Sonarr không điều khiển scan engine.
Chúng chỉ tham gia ở:

- provider item lookup
- provider refresh
- sync sau apply

### UI mới không dùng mọi state cũ

Backend vẫn còn vài field legacy như `targets` hoặc `managed_folders`, nhưng UI hiện tại không còn dùng chúng.
Chúng nên xem là phần đang chờ dọn tiếp.
