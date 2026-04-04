# Dashboard And API

## 1. Dashboard hiện tại

UI hiện có 3 view:

- `Overview`
- `Operations`
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
- `activity_log`
- `current_job`
- `report`
- `plan`
- `apply_result`
- `sync_result`

### `GET /api/process`

Trả về:

- `current_job`

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

## 7. Folder operation APIs

### `POST /api/folders/move`

Move cả folder từ source sang destination parent.

### `POST /api/folders/move-to-provider`

Move nội dung của source folder vào path mà Radarr hoặc Sonarr đang quản lý.

### `DELETE /api/folders?path=...&execute=true`

Xóa folder.

## 8. Provider APIs

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

## 9. Legacy note

Project vẫn giữ các file legacy static:

- `legacy-index.html`
- `legacy-app.js`
- `legacy-styles.css`

Nhưng hướng chính hiện tại là frontend React bundle mới.
