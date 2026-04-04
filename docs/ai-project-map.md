# AI Project Map

Tài liệu này là điểm vào nhanh cho AI hoặc người mới cần hiểu dự án mà chưa muốn đọc code ngay.

## 1. Bắt đầu từ đâu

Nếu chỉ cần nắm product shape và logic chính, ưu tiên đọc theo thứ tự:

1. tài liệu này
2. `docs/current-features.md`
3. `docs/architecture.md`
4. `docs/dashboard-and-api.md`
5. `docs/state-and-artifacts.md`

Nếu cần đi tiếp vào code, entrypoint nên xem trước là:

- frontend shell: `frontend/src/App.jsx`
- frontend API map: `frontend/src/api.js`
- shared log component: `frontend/src/components/MediaLibraryLogPanel.jsx`
- backend API entrypoint: `src/media_library_manager/web.py`
- runtime state và artifacts: `src/media_library_manager/state.py`

## 2. Product shape hiện tại

Dashboard hiện có 5 màn:

1. `Overview`
   Màn tổng quan. Gom KPI, tình trạng roots, provider, process đang chạy, các case cần chú ý, và `Recent Activity`.

2. `Media Management`
   Màn vận hành chính cho inventory folder, duplicate workflow, move folder, move vào Radarr/Sonarr, và xem process logs.

3. `Duplication Clean`
   Màn dọn duplicate ngay trong các folder đang được Radarr/Sonarr quản lý. Đây không dùng plan/apply; nó scan trực tiếp library của provider rồi cho chọn file để xóa.

4. `Library Path Repair`
   Màn sửa item của Radarr/Sonarr khi path lưu trong provider không còn tồn tại. Có scan lỗi, tìm folder phù hợp, cập nhật path, hoặc remove item khỏi provider mà không xóa media file.

5. `Settings`
   Màn cấu hình roots, SMB profiles, LAN discovery, Radarr/Sonarr, sync options, và manual sync.

## 3. Shared runtime model

### `GET /api/state`

Đây là payload tổng hợp để frontend render phần lớn UI. Payload hiện gồm:

- `roots`
- `targets`
- `integrations`
- `lan_connections`
- `managed_folders`
- `last_scan_at`
- `last_plan_at`
- `last_apply_at`
- `last_sync_at`
- `last_cleanup_at`
- `last_path_repair_at`
- `activity_log`
- `current_job`
- `report`
- `plan`
- `apply_result`
- `sync_result`
- `cleanup_report`
- `path_repair_report`

### `current_job`

Backend chỉ giữ một job đang active hoặc job mới hoàn tất gần nhất. Model chính:

- `id`
- `kind`
- `status`
- `message`
- `summary`
- `details`
- `logs`
- `cancel_requested`
- `started_at`
- `updated_at`
- `finished_at`

`summary` là progress đã normalize sẵn, tối thiểu có:

- `total`
- `completed`
- `error`
- `skipped`

Một số job bổ sung thêm field như:

- `indexed_files`
- `issues`
- `applied`
- `dry_run`

### `activity_log`

Đây là history cấp cao hơn, lưu các action vừa chạy xong hoặc đang chạy. Nó được dùng để render lịch sử gần đây và để fill log panel khi không còn live `current_job`.

Kinds thực tế đang xuất hiện gồm:

- `config`
- `lan`
- `folder`
- `scan`
- `plan`
- `apply`
- `integration`

Một số `current_job.kind` đặc thù hơn:

- `scan`
- `plan`
- `apply`
- `cleanup-scan`
- `path-repair`

### Artifact files

State và artifact hiện lưu trong `data/`:

- `app-state.json`
- `last-report.json`
- `last-plan.json`
- `last-apply.json`
- `last-sync.json`
- `last-cleanup-scan.json`
- `last-path-repair-scan.json`

## 4. Workflow chính

### 4.1 Roots và storage

App làm việc trên roots đã connect trong state.

Mỗi root có thể là:

- local path
- SMB storage root

SMB là workflow chính thức, không còn là đường vòng dựa vào mounted path.

API liên quan:

- `POST /api/roots`
- `POST /api/roots/bulk`
- `DELETE /api/roots`
- `GET /api/lan/discover`
- `GET /api/lan/connections`
- `POST /api/lan/connections`
- `POST /api/lan/connections/test`
- `GET /api/smb/browse`

### 4.2 Media Management

Media Management có 3 nhóm việc chính.

#### A. Folder inventory

Frontend load:

- `GET /api/operations/folders`
- `GET /api/operations/folders/tree`
- `GET /api/operations/folders/children`

Mục tiêu là duyệt folder con từ connected roots, lazy-load children, rồi chọn source/destination cho các thao tác.

#### B. Duplicate workflow

Luồng chính:

1. user chọn folder cần scan
2. `POST /api/scan` tạo `report`
3. `POST /api/plan` tạo `plan`
4. `POST /api/apply` chạy preview hoặc apply thật

Các điểm quan trọng:

- UI đang dùng chữ `Preview` cho mode `execute=false`
- backend/result vẫn có thể dùng từ kỹ thuật `dry-run`
- `review` action chỉ để người dùng xem lại, không được apply trực tiếp
- sau apply thật, `last-plan.json` bị xóa
- apply result vẫn giữ `plan_snapshot` để manual sync còn dùng được

#### C. Manual folder actions

Các action ngoài plan/apply:

- `POST /api/folders/move`
- `POST /api/folders/move-to-provider`
- `DELETE /api/files`
- `DELETE /api/folders`

`move-to-provider` dùng khi source là folder download còn đích là path movie/series mà provider đang quản lý.

### 4.3 Duplication Clean

Đây là workflow riêng, không dùng `report -> plan -> apply`.

Luồng:

1. user chọn provider cần scan
2. backend lấy item list từ Radarr/Sonarr
3. backend validate path từng item
4. backend scan trực tiếp các folder provider path hợp lệ
5. backend build `cleanup_report` với các group có nhiều candidate video file
6. UI cho user chọn file cần xóa, rồi gọi delete file riêng lẻ
7. sau khi xóa, UI refresh report để thấy trạng thái mới

Điểm quan trọng:

- cleanup hiện scan trên provider paths local đang tồn tại
- nó không build action plan
- group đầu tiên thường được xem là candidate nên giữ lại, còn các file dư là phần user cân nhắc xóa

API chính:

- `POST /api/cleanup/scan`
- `DELETE /api/files`

### 4.4 Library Path Repair

Workflow này cũng tách khỏi duplicate workflow.

Luồng:

1. `POST /api/path-repair/scan`
   Tìm item của Radarr/Sonarr có path bị thiếu hoặc không còn là directory hợp lệ.

2. `POST /api/path-repair/search`
   Tìm folder phù hợp trong connected roots bằng normalized title, year, và score match.

3. `POST /api/path-repair/update`
   Ghi lại path mới vào provider rồi refresh item.

4. `POST /api/path-repair/delete`
   Xóa item khỏi provider mà không xóa media files.

Điểm quan trọng:

- scan path repair hiện chỉ phát hiện item lỗi
- tìm gợi ý là một bước search riêng theo từng item
- sau update/delete, backend prune issue tương ứng ra khỏi saved repair report
- search có log realtime riêng vì đây là thao tác index/scoring có thể kéo dài

### 4.5 Settings và integrations

Settings giữ các cấu hình vận hành:

- connected roots
- SMB profiles
- Radarr config
- Sonarr config
- sync options
- manual sync

Provider layer không điều khiển scan engine. Nó chủ yếu phục vụ:

- list provider items
- move vào provider path
- refresh item sau khi đổi path
- sync sau apply execute

API chính:

- `POST /api/integrations`
- `POST /api/integrations/test`
- `GET /api/integrations/radarr/items`
- `GET /api/integrations/sonarr/items`
- `POST /api/sync`

## 5. Shared log model trong UI

UI đang dùng chung `MediaLibraryLogPanel` cho:

- `Recent Activity` trong `Overview`
- `Process Logs` trong `Media Management`
- `Cleanup Action Logs`
- `Path Repair Action Logs`

Log panel ưu tiên live `current_job.logs`, sau đó fallback sang `activity_log` đã lọc theo scope.

Nó hỗ trợ:

- filter theo level
- search text
- pause/resume stream
- clear cục bộ trên UI
- polling `/api/state` và `/api/process` khi cần

Điều này có nghĩa là khi feature nào có log/process thì nên bám vào shared log model này thay vì tự làm component log riêng.

## 6. Overview lấy số liệu từ đâu

Overview không tạo dữ liệu mới. Nó tổng hợp từ:

- `report.summary`
- `plan.summary`
- `apply_result.summary`
- `sync_result.summary`
- `cleanup_report.summary`
- `path_repair_report.summary`
- `current_job`
- `activity_log`

Một vài KPI trên overview là số dẫn xuất, không phải field backend lưu sẵn. Ví dụ:

- tổng case đã xử lý
- số lần delete file từ cleanup
- số lần sửa path provider
- số lần remove item provider

Nghĩa là nếu thay message hoặc activity kind ở backend thì cần xem lại logic tính số liệu của overview.

## 7. Legacy và các điểm cần nhớ

- `targets` và `managed_folders` vẫn còn trong state/backend nhưng không còn là workflow UI chính.
- backend vẫn serve `legacy-index.html`, `legacy-app.js`, `legacy-styles.css`, nhưng hướng chính là React bundle mới.
- Nếu thay đổi behavior của một màn, cần update luôn tài liệu này và doc liên quan để AI sau không phải quay lại đọc code.
