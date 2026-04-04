# Architecture Overview

Tài liệu này mô tả kiến trúc logic hiện tại của dự án.

## 1. Kiến trúc tổng thể

Project được tổ chức theo kiểu:

- một lõi xử lý filesystem-first
- một CLI để chạy các nghiệp vụ
- một dashboard web cục bộ để thao tác qua giao diện
- một lớp tích hợp Radarr/Sonarr chạy sau bước apply

Luồng chính:

1. người dùng khai báo roots và targets
2. scanner quét filesystem và sinh report
3. planner đọc report và sinh plan
4. operations đọc plan và apply ra filesystem
5. integrations đồng bộ lại path với Radarr/Sonarr nếu cần
6. state store lưu toàn bộ snapshot để dashboard hiển thị lại

## 2. Các module chính

### `models.py`

Chứa các dataclass lõi:

- `RootConfig`
- `MediaFile`
- `ScanReport`
- `LibraryTargets`
- `Action`

Đây là lớp dữ liệu nền cho scanner, planner, operations và state.

### `scanner.py`

Chịu trách nhiệm:

- đi qua các root
- lọc file video hợp lệ
- parse identity media
- tính quality metadata
- phát hiện exact duplicates
- phát hiện media collisions
- xác định sidecar files

### `planner.py`

Chịu trách nhiệm:

- đọc `ScanReport`
- chọn keeper cho từng group
- quyết định action `move/delete/review`
- build path đích chuẩn cho movie/series/review
- xuất plan JSON

### `operations.py`

Chịu trách nhiệm:

- đọc plan
- thực thi hoặc dry-run từng action
- move bundle gồm video và sidecar files
- delete bundle
- prune thư mục rỗng nếu bật option

### `state.py`

Chịu trách nhiệm:

- lưu state dashboard vào `app-state.json`
- lưu report/plan/apply/sync mới nhất ra file riêng
- cung cấp payload tổng hợp cho API `/api/state`
- ghi activity log

### `web.py`

Chịu trách nhiệm:

- chạy HTTP server cục bộ
- phục vụ static files của dashboard
- cung cấp các API để root UI thao tác
- kết nối dashboard với scanner, planner, operations, state và integrations

### `browser.py`

Chịu trách nhiệm:

- liệt kê mount point từ hệ điều hành
- xác định mount nào là network filesystem
- browse thư mục phục vụ LAN Browser trên dashboard

### `sync_integrations.py`

Chịu trách nhiệm:

- chuẩn hóa cấu hình integrations
- test kết nối Radarr/Sonarr
- sync path sau apply
- điều khiển root folder creation và refresh behavior

### `providers/`

Bao gồm:

- `base.py`: HTTP JSON client chung
- `radarr.py`: hành vi dành riêng cho Radarr
- `sonarr.py`: hành vi dành riêng cho Sonarr

## 3. Hai mặt vận hành của hệ thống

### CLI layer

CLI cung cấp các entrypoint:

- `scan`
- `plan`
- `apply`
- `serve`

CLI phù hợp cho:

- chạy tay
- script hóa
- automation

### Dashboard layer

Dashboard là lớp vận hành cục bộ, không phải backend service nhiều người dùng.
Nó phù hợp cho:

- cấu hình root trực quan
- browse LAN share
- xem report và plan
- theo dõi activity log

## 4. Luồng dữ liệu chính

### Scan flow

`RootConfig[] -> scanner.scan_roots() -> ScanReport -> report.json`

### Plan flow

`ScanReport + LibraryTargets -> planner.plan_actions() -> plan.json`

### Apply flow

`plan.json -> operations.apply_plan() -> apply result JSON`

### Sync flow

`plan + apply_result + integrations -> sync_after_apply() -> sync result JSON`

## 5. Nguyên tắc thiết kế hiện tại

### Filesystem-first

Project ưu tiên sự thật trên ổ đĩa trước, thay vì phụ thuộc vào metadata của Radarr/Sonarr.

### Safe by default

Mặc định là dry-run.
Điều này làm cho cleanup an toàn hơn khi heuristic parse chưa chắc chắn 100%.

### Machine-readable outputs

Các bước scan, plan, apply và sync đều tạo payload JSON rõ ràng để:

- debug
- audit
- tái sử dụng trong tooling khác

### Local and self-contained

Web dashboard chạy bằng HTTP server tiêu chuẩn trong Python, không phụ thuộc framework web ngoài.

## 6. Những điểm coupling quan trọng

- `scanner.py` quyết định chất lượng dữ liệu đầu vào cho mọi bước sau
- `planner.py` phụ thuộc mạnh vào `media_key`, `canonical_name`, `quality_rank`
- `operations.py` giả định plan hợp lệ và không tự tái diễn giải logic nghiệp vụ
- `sync_integrations.py` phụ thuộc vào `action.details` và `media_key` để biết item thuộc Radarr hay Sonarr
- `state.py` là nguồn tổng hợp cho toàn bộ dashboard

## 7. Những điểm cần cẩn trọng khi mở rộng

- thay đổi parse logic trong scanner sẽ làm đổi grouping và chất lượng plan
- thay đổi canonical path builder sẽ ảnh hưởng sync Radarr/Sonarr
- thay đổi JSON schema của report/plan/apply có thể làm dashboard hoặc tooling phụ thuộc bị lệch
- web handler đang là synchronous request model, nên scan/apply lớn sẽ chiếm request thread trong lúc chạy
