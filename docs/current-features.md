# Current Features

## 1. Frontend hiện tại

Frontend hiện tại là React + Ant Design.

Dashboard có 5 view:

- `Overview`
- `Library Finder`
- `Library Cleanup`
- `Library Path Repair`
- `Settings`

## 2. Overview

Overview là màn giám sát tổng hợp.

Hiện hiển thị:

- KPI inventory ổn định hơn, tập trung vào:
  - `Connected Roots`
  - `Indexed Folders`
  - `Provider Library`
  - `Tracked Media Files`
- số liệu folder index lấy từ artifact cache `last-folder-index.json` qua `last_folder_index_at` và `folder_index_summary`
- số liệu provider inventory được derive từ danh sách item hiện tại của Radarr và Sonarr
- trạng thái roots và providers
- current process
- recent activity
- các breakdown phụ về resolution và attention vẫn được tổng hợp từ artifact `last-*` lẫn `activity_log`, nên các thao tác như `Folder deleted.`, `Provider item removed.`, hoặc `Provider path updated.` vẫn phản ánh trên dashboard

## 3. Library Finder

Đây là màn vận hành chính để duyệt library và thao tác với file hoặc folder.

Hiện có:

- folder inventory phẳng từ `GET /api/operations/folders`
- folder tree từ `GET /api/operations/folders/tree`
- lazy child loading từ `GET /api/operations/folders/children`
- manual refresh của `Library Finder` hiện rebuild thêm `folder index` artifact cho connected roots để tái dùng ở các workflow search nặng
- duplicate folder cleanup scan từ selection hiện tại trong `Library Finder` cho local, SMB, và rclone roots
- xóa duplicate folder candidates ngay trong `Library Finder` với shared process logs và retry/resume
- duplicate workflow `scan -> plan -> preview/apply`
- move folder
- delete file / delete folder
- move folder contents vào provider-managed path
- shared process logs

## 4. Library Cleanup

Đây là workflow cleanup riêng cho duplicate files trong thư viện Radarr/Sonarr. Nó tách khỏi duplicate workflow trong `Library Finder`.

Hiện có:

- một mode `Provider Duplicate Files` để scan folder từ các path mà Radarr/Sonarr đang quản lý
- nếu provider path không tồn tại trong runtime local, backend thử resolve qua connected SMB roots
- build group có nhiều candidate video file trong cùng folder
- chọn file cần xóa
- refresh report sau khi delete
- saved cleanup reports vẫn còn sau khi refresh trình duyệt
- shared cleanup logs

Cleanup không dùng `plan` và `apply`.

## 5. Library Path Repair

Đây là workflow sửa item provider bị hỏng path.

Hiện có:

- scan item Radarr/Sonarr có path lỗi
- scan report hiện chỉ lấy theo trạng thái `missing` mà chính Radarr/Sonarr báo, không còn tự so sánh connected roots để suy luận `path_not_found`
- với Radarr, scan chỉ đưa vào report các movie đã available/released và đang bị `missing` trong provider
- với Sonarr, scan chỉ đưa vào report các series mà provider đang báo thiếu episode files theo thống kê của Sonarr
- với Sonarr, search và path-mapping hiện kiểm tra cả rclone lẫn SMB series roots, kể cả alias Synology-style như `usbshare/Series`
- search hiện ưu tiên đọc `folder index` artifact đã cache từ `Library Finder` refresh, rồi mới fallback sang live traversal nếu cache không có candidate phù hợp
- search folder phù hợp trong connected roots khi user chủ động bấm tìm
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
- rclone remote (identified by a `storage_uri` like `rclone://remote/path`)

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
- `available_actions` cho `cancel`, `wait`, `retry`, `resume` khi job hỗ trợ

Refresh trang vẫn thấy trạng thái job hoặc activity mới nhất.

## 11. Cancel job

Backend hiện hỗ trợ:

- `POST /api/process/cancel`

Cancel là cooperative:

- state đổi sang `cancel_requested`
- log ghi cancel request
- job dừng ở safe point tiếp theo

## 12. Retry, Wait, Resume

Các job nặng hiện có thể lưu lại `job_control` context để chạy lại cùng payload cũ.

Hiện hỗ trợ:

- `POST /api/process/wait`
- `POST /api/process/retry`
- `POST /api/process/resume`

`wait` chuyển job lỗi hoặc cancelled sang trạng thái `waiting` để user tiếp tục sau.

`retry` rerun cùng workflow với payload cũ.

`resume` hiện đã dùng checkpoint mức root/provider cho các scan nặng, nên có thể tiếp tục từ root hoặc provider kế tiếp thay vì luôn quét lại toàn bộ. Nó chưa resume sâu đến mức từng file.

## 13. Những gì không còn là workflow UI chính

UI hiện tại không còn xem các khối sau là đường đi chính:

- `Canonical Targets`
- `Managed SMB Folders`

Backend vẫn còn giữ field hoặc API cũ liên quan, nhưng AI nên xem đó là phần legacy hoặc phụ trợ.
