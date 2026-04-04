# Dashboard And API

Tài liệu này mô tả dashboard web cục bộ và các API mà giao diện đang sử dụng.

## 1. Cách dashboard hoạt động

Dashboard chạy trên `ThreadingHTTPServer` của Python.
Server phục vụ:

- static HTML/CSS/JS
- API JSON cho cấu hình và vận hành

Điểm cần lưu ý:

- đây là local admin dashboard
- không có auth layer
- không có database ngoài JSON file state

## 2. Static assets

Dashboard hiện dùng các file:

- `static/index.html`
- `static/styles.css`
- `static/app.js`
- `static/favicon.svg`

Các endpoint static:

- `GET /`
- `GET /favicon.svg`
- `GET /app.js`
- `GET /styles.css`

## 3. Các view hiện có trên dashboard

Navigation hiện có:

- `Overview`
- `Library Roots`
- `Integrations`
- `LAN Browser`
- `Duplicate Report`
- `Action Plan`
- `Activity Log`

## 4. Mô tả từng view

### Overview

Hiển thị:

- last scan / last plan / last apply
- số file đã index
- số exact duplicate groups
- số media collisions
- số move/delete actions
- lỗi apply gần nhất
- configured roots
- mounted LAN shares
- recent activity

### Library Roots

Cho phép:

- thêm root mới
- nhập `path`, `label`, `priority`, `kind`
- lưu canonical targets
- xóa root khỏi danh sách scan

### Integrations

Cho phép:

- cấu hình Radarr
- cấu hình Sonarr
- lưu sync options
- test connectivity
- xem kết quả sync gần nhất

### LAN Browser

Cho phép:

- browse filesystem đang truy cập được từ máy
- xem favorites từ mount points mạng
- đi theo breadcrumb
- chọn thư mục hiện tại để đưa vào form root

### Duplicate Report

Hiển thị:

- exact duplicate groups
- media collision groups

### Action Plan

Hiển thị:

- toàn bộ actions hiện có trong plan
- kết quả apply gần nhất
- trạng thái integration sync gần nhất

### Activity Log

Hiển thị:

- timeline sự kiện
- chi tiết JSON của từng event

## 5. API state và system

### `GET /api/state`

Trả về payload tổng hợp từ `StateStore.api_payload()`:

- roots
- targets
- integrations
- timestamps
- activity_log
- report
- plan
- apply_result
- sync_result

### `GET /api/system/mounts`

Trả về danh sách mount point nhìn thấy từ máy.
Mỗi mount gồm:

- `source`
- `mount_point`
- `filesystem`
- `is_network`
- `label`

### `GET /api/browse?path=...`

Trả về nội dung thư mục:

- path hiện tại
- parent
- mount khớp nhất
- breadcrumbs
- entries
- overflow
- favorites

Nếu path không hợp lệ, API trả lỗi `400`.

## 6. API cấu hình

### `POST /api/roots`

Thêm hoặc cập nhật một root scan.
Payload gồm:

- `path`
- `label`
- `priority`
- `kind`

Điều kiện:

- path phải là directory tồn tại

### `DELETE /api/roots?path=...`

Xóa root khỏi danh sách cấu hình hiện tại.

### `POST /api/targets`

Lưu:

- `movie_root`
- `series_root`
- `review_root`

## 7. API integrations

### `POST /api/integrations`

Lưu cấu hình:

- `radarr`
- `sonarr`
- `sync_options`

### `POST /api/integrations/test`

Test kết nối Radarr/Sonarr bằng cấu hình mới truyền lên hoặc cấu hình đang lưu.

### `POST /api/sync`

Chạy sync thủ công sau apply.

Điều kiện:

- phải có `plan`
- phải có `apply_result`

## 8. API scan, plan, apply

### `POST /api/scan`

Hành vi:

1. kiểm tra phải có root
2. ghi activity `running`
3. chạy `scan_roots()`
4. lưu report
5. ghi activity `success` hoặc `error`

### `POST /api/plan`

Hành vi:

1. kiểm tra phải có report
2. đọc option `delete_lower_quality`
3. ghi activity `running`
4. chạy `plan_actions()`
5. lưu plan
6. ghi activity `success` hoặc `error`

### `POST /api/apply`

Hành vi:

1. kiểm tra phải có plan
2. đọc `execute` và `prune_empty_dirs`
3. ghi activity `running`
4. chạy `apply_plan()`
5. nếu execute thì chạy `sync_after_apply()`
6. lưu apply result và sync result
7. ghi activity `success` hoặc `error`

## 9. Activity log

Dashboard ghi activity cho các loại event:

- `config`
- `scan`
- `plan`
- `apply`
- `integration`

Mỗi event hiện có:

- `id`
- `kind`
- `status`
- `message`
- `created_at`
- `details`

## 10. Một số giới hạn của dashboard hiện tại

- không có user/session/auth
- request chạy đồng bộ theo handler, không có queue job nền riêng
- report/plan list trên UI đang chỉ render một số lượng item giới hạn để tránh quá nặng giao diện
- browse API giới hạn tối đa 300 entries cho mỗi thư mục
