# Current Features

## 1. Frontend hiện tại

Frontend hiện tại là React + Ant Design.

Dashboard có 5 view:

- `Overview`
- `Library Finder`
- `Duplication Clean`
- `Library Path Repair`
- `Settings`

## 2. Overview

Overview là màn giám sát tổng hợp.

Hiện hiển thị:

- KPI về duplicate, apply, sync, cleanup, path repair
- trạng thái roots và providers
- current process
- recent activity
- các số liệu dẫn xuất như số case đã xử lý

## 3. Library Finder

Đây là màn vận hành chính để duyệt library và thao tác với file hoặc folder.

Hiện có:

- folder inventory phẳng từ `GET /api/operations/folders`
- folder tree từ `GET /api/operations/folders/tree`
- lazy child loading từ `GET /api/operations/folders/children`
- duplicate workflow `scan -> plan -> preview/apply`
- move folder
- delete file / delete folder
- move folder contents vào provider-managed path
- shared process logs

## 4. Duplication Clean

Đây là workflow cleanup riêng với 2 mode.

Hiện có:

- mặc định mở vào mode `Empty Duplicate Folders` để ưu tiên dọn folder rác
- mode `Duplicate Files` để scan folder từ các path mà Radarr/Sonarr đang quản lý
- có option mặc định bật để khi scan provider duplicates thì refresh luôn report `Empty Duplicate Folders`
- nếu provider path không tồn tại trong runtime local, backend thử resolve qua connected SMB roots
- build group có nhiều candidate video file trong cùng folder
- chọn file cần xóa
- mode `Empty Duplicate Folders` để so khớp folder top-level trùng tên giữa nhiều connected roots
- inspect đệ quy chỉ trên các duplicate groups để xác định copy nào không có video
- đánh dấu các folder `empty` hoặc `sidecar-only` là candidate để xóa
- auto-select các folder `Delete Candidate` khi user mở một group để dọn nhanh hơn
- xóa folder candidate rồi refresh lại report riêng của empty-folder cleanup
- refresh report sau khi delete trong từng mode
- saved cleanup reports vẫn còn sau khi refresh trình duyệt
- shared cleanup logs

Cleanup không dùng `plan` và `apply`.

## 5. Library Path Repair

Đây là workflow sửa item provider bị hỏng path.

Hiện có:

- scan item Radarr/Sonarr có path lỗi
- scan path-aware qua connected SMB roots để tránh false positive khi provider dùng path kiểu NAS/container khác runtime app
- search folder phù hợp trong connected roots
- update path trong provider
- remove item khỏi provider mà không xóa media files
- shared repair logs
- realtime search progress cho thao tác search

## 6. Settings

Settings giữ toàn bộ cấu hình vận hành.

Hiện có:

- connected roots
- SMB profiles
- LAN discovery
- Radarr settings
- Sonarr settings
- sync options
- manual sync

## 7. Connected roots và SMB

App làm việc trên các root đã connect vào state.

Mỗi root hiện có thể là:

- local path
- SMB storage root

Mỗi root có thể mang:

- `path`
- `label`
- `priority`
- `kind`
- `connection_id`
- `connection_label`
- `storage_uri`
- `share_name`

SMB là workflow first-class, không phải chỉ là helper cho mounted path.

## 8. Duplicate workflow

App vẫn có đầy đủ:

- `scan`
- `plan`
- `apply`

`scan` hỗ trợ local và SMB roots thông qua storage abstraction.

`apply` hiện có hai mode:

- `Preview` trong UI, tương ứng `execute=false`
- `Apply Changes` trong UI, tương ứng `execute=true`

## 9. Radarr / Sonarr

App hiện hỗ trợ:

- save provider settings
- test provider connectivity
- list provider items
- move vào provider path
- sync sau apply execute
- sync thủ công
- cleanup scan
- path repair

## 10. Shared log và current job

Các workflow dài như scan, plan, apply, cleanup scan, path repair scan/search hiện dùng chung model:

- persisted `current_job`
- detailed `logs`
- `summary`
- `details`
- `cancel_requested`
- `activity_log`

Refresh trang vẫn thấy trạng thái job hoặc activity mới nhất.

## 11. Cancel job

Backend hiện hỗ trợ:

- `POST /api/process/cancel`

Cancel là cooperative:

- state đổi sang `cancel_requested`
- log ghi cancel request
- job dừng ở safe point tiếp theo

## 12. Những gì không còn là workflow UI chính

UI hiện tại không còn xem các khối sau là đường đi chính:

- `Canonical Targets`
- `Managed SMB Folders`

Backend vẫn còn giữ field hoặc API cũ liên quan, nhưng AI nên xem đó là phần legacy hoặc phụ trợ.
