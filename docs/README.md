# Project Documentation

Thư mục `docs/` mô tả logic hiện tại của dự án theo product shape mới:

- `Operations` là nơi chạy scan, review duplicate, build plan, apply, và move folder thủ công
- `Settings` là nơi quản lý SMB profiles, connected folders, và Radarr/Sonarr

## Danh mục

- [current-features.md](./current-features.md)
  Tập hợp các tính năng hiện có theo góc nhìn người dùng.

- [architecture.md](./architecture.md)
  Kiến trúc module, luồng dữ liệu, và quan hệ giữa dashboard, state, scanner, planner, operations, integrations.

- [dashboard-and-api.md](./dashboard-and-api.md)
  Cấu trúc dashboard 2 page và các API nội bộ mà frontend đang dùng.

- [state-and-artifacts.md](./state-and-artifacts.md)
  Cách state và các artifact JSON được lưu.

- [integrations.md](./integrations.md)
  Logic giữ kết nối Radarr/Sonarr trong `Settings` và đồng bộ path sau `apply`.

- [planning-and-apply.md](./planning-and-apply.md)
  Cách hệ thống chuyển scan report thành action plan và áp dụng thay đổi trên filesystem, cùng manual folder move.

- [scanning-and-detection.md](./scanning-and-detection.md)
  Chi tiết logic scan filesystem và phát hiện duplicate.

- [cli-and-config.md](./cli-and-config.md)
  Cách dùng CLI và cấu hình từ command line hoặc TOML.

## Cách đọc nhanh

Nếu cần nắm product hiện tại:

1. đọc `current-features.md`
2. đọc `architecture.md`
3. đọc `dashboard-and-api.md`

Nếu cần đi sâu vào logic scan và apply:

1. đọc `scanning-and-detection.md`
2. đọc `planning-and-apply.md`
3. đọc `integrations.md`

## Phạm vi

Các tài liệu trong thư mục này mô tả hành vi hiện tại của codebase sau khi dashboard được rút về 2 page `Operations` và `Settings`.
