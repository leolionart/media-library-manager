# Documentation

Thư mục `docs/` mô tả trạng thái hiện tại của dự án sau khi:

- frontend được viết lại bằng React + Ant Design
- backend chuyển mạnh sang SMB-native
- folder inventory có cả list và tree
- current job có log chi tiết, cancel request, và persist qua refresh
- dashboard có 5 màn chính và dùng chung log component cho các flow dài

## Danh mục

- [ai-project-map.md](./ai-project-map.md)
  Tài liệu AI-first: bản đồ tính năng, workflow, state, artifact, API, và những điểm cần biết trước khi đọc code.

- [architecture.md](./architecture.md)
  Kiến trúc tổng thể, module chính, và luồng dữ liệu.

- [current-features.md](./current-features.md)
  Các tính năng hiện có theo góc nhìn product và user flow.

- [dashboard-and-api.md](./dashboard-and-api.md)
  Cấu trúc UI hiện tại và API nội bộ frontend đang dùng.

- [scanning-and-detection.md](./scanning-and-detection.md)
  Logic scan, duplicate detection, storage abstraction, và cancel behavior.

- [planning-and-apply.md](./planning-and-apply.md)
  Build plan, apply, move folder, move-to-provider, và sync.

- [integrations.md](./integrations.md)
  Cấu hình Radarr/Sonarr, test connectivity, provider item list, và sync.

- [state-and-artifacts.md](./state-and-artifacts.md)
  State persistence, artifact JSON, current job model, activity log.

- [cli-and-config.md](./cli-and-config.md)
  CLI hiện có, config file, và quan hệ giữa CLI với dashboard runtime.

## Cách đọc nhanh

Nếu cần nắm dự án hiện tại:

1. đọc `ai-project-map.md`
2. đọc `current-features.md`
3. đọc `architecture.md`
4. đọc `dashboard-and-api.md`

Nếu cần backend behavior:

1. đọc `ai-project-map.md`
2. đọc `scanning-and-detection.md`
3. đọc `planning-and-apply.md`
4. đọc `integrations.md`
5. đọc `state-and-artifacts.md`
