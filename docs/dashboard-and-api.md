# Dashboard And API

## 1. Dashboard hiện tại

UI hiện có 5 view:

- `Overview`
- `Library Finder`
- `Library Cleanup`
- `Library Path Repair`
- `Settings`

Static assets được backend serve từ:

- [src/media_library_manager/static/index.html](/Volumes/DATA/Coding Projects/media-library-manager/src/media_library_manager/static/index.html)
- [src/media_library_manager/static/app.js](/Volumes/DATA/Coding Projects/media-library-manager/src/media_library_manager/static/app.js)
- [src/media_library_manager/static/styles.css](/Volumes/DATA/Coding Projects/media-library-manager/src/media_library_manager/static/styles.css)

Source frontend:

- [frontend/](/Volumes/DATA/Coding Projects/media-library-manager/frontend)

## 2. State và process APIs

### `GET /api/state`

Payload tổng hợp cho frontend:

- `roots`
- `integrations`
- `lan_connections`
- `last_scan_at`
- `last_plan_at`
- `last_apply_at`
- `last_sync_at`
- `last_cleanup_at`
- `activity_log`
- `current_job`
- `report`
- `plan`
- `apply_result`
- `sync_result`
- `cleanup_report`
- `last_empty_folder_cleanup_at`
- `empty_folder_cleanup_report`
- `last_path_repair_at`
- `path_repair_report`
- `last_folder_index_at`
- `folder_index_summary`

### `GET /api/process`

Trả về:

- `current_job`

### `GET /api/system/mounts`

Trả về danh sách mounts local mà frontend có thể dùng để tham chiếu nhanh khi chọn path.

### `POST /api/process/cancel`

Yêu cầu hủy job đang chạy.

Kết quả:

- set `cancel_requested = true`
- update `message`
- append warning log

## 3. Roots APIs

### `POST /api/roots`

Thêm một root.

### `POST /api/roots/bulk`

Thêm nhiều roots cùng lúc.

### `DELETE /api/roots?path=...`

Xóa root khỏi state.

## 4. SMB APIs

### `GET /api/lan/connections`

Lấy SMB profiles đã lưu.

### `POST /api/lan/connections`

Lưu SMB profile.

### `POST /api/lan/connections/test`

Test profile bằng `smbclient`.

### `DELETE /api/lan/connections?id=...`

Xóa SMB profile.

### `GET /api/smb/browse`

Browse SMB host hoặc share.

Query thường dùng:

- `connection_id`
- `share_name`
- `path`
- `scope=host`

## 5. Operations folder APIs

### `GET /api/operations/folders`

Trả inventory phẳng của folder con bên trong roots.

### `GET /api/operations/folders/children`

Trả child nodes cho một tree node cụ thể.

Query bắt buộc:

- `storage_uri`
- `root_storage_uri`

### `GET /api/operations/folders/tree?depth=...`

Trả cấu trúc tree theo root.

Node hiện có:

- `label`
- `key`
- `path`
- `display_path`
- `storage_uri`
- `depth`
- `has_children`
- `children`

### `POST /api/operations/folder-index/refresh`

Rebuild cached folder metadata from connected roots.
`Library Finder` refresh hiện gọi endpoint này để các search nặng như `Path Repair Search` có thể đọc artifact trước thay vì luôn full-scan live roots.

Payload:

- `max_depth`

## 6. Duplicate workflow APIs

### `POST /api/scan`

Scan tất cả roots hiện có.

### `POST /api/plan`

Build plan từ latest report.

Payload:

- `delete_lower_quality`

### `POST /api/apply`

Apply latest plan.

Payload:

- `execute`
- `prune_empty_dirs`

Lưu ý:

- `execute=false` là preview mode
- `execute=true` là apply thật
- apply execute sẽ clear saved plan

## 7. Cleanup APIs

Cleanup UI hiện tập trung vào:

- `Provider Duplicate Files`

### `POST /api/cleanup/scan`

Scan trực tiếp provider-managed folders để build cleanup report.

Payload:

- `providers`

### `POST /api/cleanup/empty-folders/scan`

Scan các folder top-level trùng tên giữa nhiều connected roots, rồi build report riêng cho các copy không có video.

Payload:

- body rỗng

## 8. Path Repair APIs

### `POST /api/path-repair/scan`

Scan item Radarr/Sonarr mà chính provider đang báo `missing`.
Flow này không còn tự so sánh connected roots hoặc local path để suy luận `path_not_found`.
Với Radarr, scan chỉ đưa vào report các movie đã available/released và đang `missing` trong provider để tránh lẫn các item chưa phát hành hoặc đã có file.
Với Sonarr, scan chỉ đưa vào report các series mà thống kê của Sonarr cho thấy chưa có episode files.

### `POST /api/path-repair/search`

Search folder phù hợp trong connected roots để user chọn thư mục đúng rồi cập nhật lại provider path.
Với Sonarr, search hiện đi qua cả rclone và SMB series roots thay vì bỏ SMB khi có rclone root.
Search hiện ưu tiên dùng `last-folder-index.json` đã cache; chỉ fallback sang live traversal khi cache chưa có kết quả đủ tốt.

Payload:

- `provider`
- `query`

### `POST /api/path-repair/update`

Update provider item sang path mới.

Payload:

- `provider`
- `item_id`
- `path`

### `POST /api/path-repair/delete`

Remove provider item mà không xóa media files.

Payload:

- `provider`
- `item_id`
- `add_import_exclusion`

## 9. Folder operation APIs

### `POST /api/folders/move`

Move cả folder từ source sang destination parent.

### `POST /api/folders/move-to-provider`

Move nội dung của source folder vào path mà Radarr hoặc Sonarr đang quản lý.

### `DELETE /api/folders?path=...&execute=true`

Xóa folder.

Route này cũng được dùng để xóa các empty duplicate folder candidates.

### `DELETE /api/files?...`

Xóa file media đơn lẻ.

Query thường dùng:

- `path`
- `storage_uri`
- `root_path`
- `root_storage_uri`
- `prune_empty_dirs`

## 10. Provider APIs

### `POST /api/integrations`

Lưu Radarr/Sonarr settings.

### `POST /api/integrations/test`

Test connectivity của providers.

### `POST /api/sync`

Manual sync sau apply result.

### `GET /api/integrations/radarr/items`

Lấy movie list.

### `GET /api/integrations/sonarr/items`

Lấy series list.

## 11. Legacy note

Project vẫn giữ các file legacy static:

- `legacy-index.html`
- `legacy-app.js`
- `legacy-styles.css`

Nhưng hướng chính hiện tại là frontend React bundle mới.
