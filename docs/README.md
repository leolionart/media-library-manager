# Project Documentation

Thư mục `docs/` tập hợp tài liệu mô tả logic hiện tại và các tính năng đang có của dự án `media-library-manager`.

## Danh mục

- [current-features.md](./current-features.md)
  Tổng quan các tính năng hiện có, nhóm theo góc nhìn người dùng và vận hành.

- [architecture.md](./architecture.md)
  Kiến trúc module, luồng dữ liệu chính, và vai trò của từng thành phần trong codebase.

- [cli-and-config.md](./cli-and-config.md)
  Giải thích cách CLI hoạt động, cách nạp root/target từ tham số hoặc file TOML.

- [scanning-and-detection.md](./scanning-and-detection.md)
  Logic scan filesystem, parse tên media, phát hiện duplicate và cách chấm điểm chất lượng.

- [planning-and-apply.md](./planning-and-apply.md)
  Cách build action plan, chọn keeper, và áp dụng `move/delete/review` với `dry-run` hoặc `execute`.

- [dashboard-and-api.md](./dashboard-and-api.md)
  Giải thích dashboard web, các view hiện có và toàn bộ HTTP API nội bộ.

- [state-and-artifacts.md](./state-and-artifacts.md)
  Cách state được lưu, các file JSON đầu ra và activity log.

- [integrations.md](./integrations.md)
  Logic tích hợp Radarr/Sonarr, test kết nối, đồng bộ path sau apply và các giới hạn hiện tại.

## Cách đọc

Nếu cần nắm nhanh dự án:

1. Đọc `current-features.md`
2. Đọc `architecture.md`
3. Đọc `scanning-and-detection.md`
4. Đọc `planning-and-apply.md`

Nếu cần vận hành dashboard và integrations:

1. Đọc `dashboard-and-api.md`
2. Đọc `state-and-artifacts.md`
3. Đọc `integrations.md`

## Phạm vi

Các tài liệu trong thư mục này mô tả hành vi hiện tại của code tại thời điểm viết tài liệu.
Chúng không cố mô tả roadmap hoặc tính năng tương lai.
