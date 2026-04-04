# Dashboard And API

Tài liệu này mô tả dashboard 2 page và các API nội bộ mà frontend đang dùng.

## 1. Dashboard layout

Dashboard hiện chỉ có 2 page:

- `Operations`
- `Settings`

### Operations

Hiển thị:

- folder list là workspace chính
- action dropdown trên từng connected folder row
- manual folder move form
- connected folders overview
- duplicate workflow controls
- duplicate results
- action plan
- apply result
- process logs
- recent activity

### Settings

Hiển thị:

- connected folders list
- add-folder modal
- SMB profile form và danh sách profile
- Radarr form
- Sonarr form
- integration options
- integration status

## 2. Static assets

Dashboard dùng:

- `static/index.html`
- `static/styles.css`
- `static/app.js`
- `static/favicon.svg`

## 3. API state và process

### `GET /api/state`

Trả về payload tổng hợp:

- `roots`
- `targets`
- `integrations`
- `lan_connections`
- `report`
- `plan`
- `apply_result`
- `sync_result`
- timestamps
- `activity_log`
- `current_job`

### `GET /api/process`

Trả về:

- `current_job`

Frontend poll endpoint này khi scan/plan/apply đang chạy.

## 4. API connected folders

### `POST /api/roots`

Thêm hoặc cập nhật connected folder.

Payload:

- `path`
- `label`
- `priority`
- `kind`
- `connection_id`
- `connection_label`

Lưu ý:

- path phải là directory tồn tại và runtime phải truy cập được

### `DELETE /api/roots?path=...`

Xóa connected folder khỏi state.

## 5. API SMB profiles

### `GET /api/lan/connections`

Lấy danh sách SMB profiles đã lưu.

### `POST /api/lan/connections`

Lưu SMB profile.

### `POST /api/lan/connections/test`

Test profile bằng `smbclient`.

### `DELETE /api/lan/connections?id=...`

Xóa SMB profile.

## 6. API duplicate workflow

### `POST /api/scan`

Scan tất cả connected folders hiện có.

### `POST /api/plan`

Build plan từ latest report.

Payload hiện dùng:

- `delete_lower_quality`

### `POST /api/apply`

Apply plan hiện tại.

Payload hiện dùng:

- `execute`
- `prune_empty_dirs`

## 7. API manual folder move

### `POST /api/folders/move`

Preview hoặc execute một folder move độc lập với duplicate planner.

Payload:

- `source`
- `destination_parent`
- `execute`

Hành vi:

- nếu `execute=false` thì trả preview
- nếu `execute=true` thì move thật thư mục vào destination parent

### `POST /api/folders/move-to-provider`

Move nội dung của một source folder vào path đã được Radarr hoặc Sonarr quản lý.

Payload:

- `provider`
- `source`
- `item_id`
- `destination`
- `execute`

Hành vi:

- nếu `execute=false` thì trả preview
- nếu `execute=true` thì move nội dung source folder vào destination hiện có
- sau đó gọi refresh provider tương ứng

### `DELETE /api/folders?path=...&execute=true`

Xóa một folder khỏi filesystem.

Hiện tại:

- nếu `execute=false` thì trả preview delete
- nếu `execute=true` thì xóa recursive bằng backend operation

## 8. API integrations

### `POST /api/integrations`

Lưu cấu hình Radarr/Sonarr.

### `POST /api/integrations/test`

Test connectivity của integrations.

### `POST /api/sync`

Chạy sync thủ công dựa trên latest plan và latest apply result.

### `GET /api/integrations/radarr/items`

Lấy movie list hiện có từ Radarr để dùng cho modal `Move To Radarr...`

### `GET /api/integrations/sonarr/items`

Lấy series list hiện có từ Sonarr để dùng cho modal `Move To Sonarr...`
