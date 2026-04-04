# Architecture Overview

Tài liệu này mô tả kiến trúc logic hiện tại của dự án.

## 1. Kiến trúc tổng thể

Project vẫn là một hệ thống filesystem-first, nhưng bề mặt vận hành được tổ chức lại thành 2 lớp dashboard rõ ràng:

- `Operations`: chạy scan, review duplicate, build/apply plan, và move folder thủ công
- `Settings`: quản lý SMB profiles, connected folders, và Radarr/Sonarr

Luồng chính hiện tại:

1. người dùng cấu hình SMB profiles và connected folders trong `Settings`
2. connected folders được lưu dưới dạng scan roots có thêm metadata SMB profile
3. `scanner.py` quét các roots này và sinh report duplicate
4. `planner.py` build plan `move/delete/review`
5. `operations.py` apply plan hoặc preview
6. `operations.py` cũng cung cấp manual folder move cho use case cut/paste folder từ A sang B
7. `sync_integrations.py` đồng bộ path về Radarr/Sonarr sau apply execute hoặc sync thủ công
8. `state.py` lưu mọi snapshot để dashboard render lại sau restart

## 2. Các module chính

### `models.py`

Chứa dataclass lõi:

- `RootConfig`
- `MediaFile`
- `ScanReport`
- `LibraryTargets`
- `Action`

`RootConfig` hiện ngoài `path/label/priority/kind` còn có:

- `connection_id`
- `connection_label`

Hai field này giúp dashboard biết connected folder nào thuộc SMB profile nào, nhưng engine scan vẫn làm việc trên filesystem path thực tế. Popup add folder sẽ cố match SMB profile với mounted path hiện có để giảm nhập tay phần runtime path.

### `scanner.py`

Chịu trách nhiệm:

- đi qua từng connected folder
- index video files
- phát hiện exact duplicates
- phát hiện media collisions

### `planner.py`

Biến `ScanReport` thành plan JSON gồm:

- `move`
- `delete`
- `review`

### `operations.py`

Chứa hai nhóm thao tác:

- apply plan từ duplicate workflow
- move folder thủ công bằng kiểu cut/paste từ source sang destination parent
- move contents của folder download vào folder đang được provider quản lý
- delete folder

### `state.py`

Lưu:

- connected folders
- SMB profiles
- integration settings
- latest report/plan/apply/sync
- activity log
- current job

### `web.py`

Phục vụ:

- static dashboard
- API cho `Operations`
- API cho `Settings`

### `lan_connections.py`

Quản lý:

- SMB profile persistence
- connection test qua `smbclient`
- SMB folder helper cho browse/create/delete khi cần

### `sync_integrations.py`

Giữ logic:

- normalize cấu hình Radarr/Sonarr
- test connectivity
- sync path sau apply execute

## 3. Hai mặt vận hành của dashboard

### `Operations`

Đây là working layer.

Nó tập trung vào:

- xem connected folders
- preview manual folder move
- execute manual folder move
- run scan
- review duplicate findings
- build plan
- dry-run apply
- execute apply
- theo dõi process logs và activity

### `Settings`

Đây là support layer.

Nó tập trung vào:

- save nhiều SMB profiles với credential khác nhau
- add connected folders qua modal
- gán connected folder với SMB profile khi cần
- cấu hình Radarr
- cấu hình Sonarr
- cấu hình sync options

## 4. Luồng dữ liệu chính

### Connected folder setup

`Settings form -> /api/roots -> StateStore -> app-state.json`

### Scan flow

`connected roots -> scanner.scan_roots() -> ScanReport -> last-report.json`

### Plan flow

`ScanReport + LibraryTargets -> planner.plan_actions() -> last-plan.json`

### Apply flow

`last-plan.json -> operations.apply_plan() -> last-apply.json`

### Manual move flow

`Operations form -> /api/folders/move -> operations.move_folder()`

### Provider move flow

`Folder list action -> /api/integrations/<provider>/items -> /api/folders/move-to-provider -> operations.move_folder_contents() -> provider refresh`

### Sync flow

`plan + apply_result + integrations -> sync_after_apply() -> last-sync.json`

## 5. Nguyên tắc thiết kế hiện tại

### Filesystem-first

Project ưu tiên trạng thái thật trên ổ đĩa trước.
SMB profile chỉ là lớp kết nối hỗ trợ setup; scan/apply vẫn dựa vào path mà runtime đọc và ghi được.

### Operations vs Settings

Mọi thứ gây nhiễu vận hành được dồn về `Settings`.
`Operations` chỉ giữ lại hành động mà người dùng thực sự làm hàng ngày.

### Safe by default

- duplicate workflow vẫn có dry-run
- manual folder move có preview trước execute

## 6. Những coupling quan trọng

- `RootConfig.path` vẫn là input thật cho scanner
- metadata SMB trong `RootConfig` chỉ hỗ trợ bề mặt dashboard, không thay thế filesystem path
- `planner.py` vẫn phụ thuộc vào scan report và target roots
- `sync_integrations.py` vẫn phụ thuộc vào plan/apply result
- frontend `app.js` phụ thuộc trực tiếp vào payload từ `StateStore.api_payload()`
