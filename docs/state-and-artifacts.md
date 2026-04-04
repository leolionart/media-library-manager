# State And Artifacts

Tài liệu này mô tả cách project lưu state và các file JSON trung gian/phục vụ dashboard.

## 1. Mục tiêu của state store

`StateStore` là lớp lưu trạng thái vận hành hiện tại của dashboard.
Nó giúp app:

- nhớ roots và targets
- nhớ cấu hình integrations
- giữ snapshot của các lần scan/plan/apply/sync gần nhất
- hiển thị lại mọi thứ sau khi restart

## 2. Các file được sử dụng

Giả sử `state_file` là:

```text
./data/app-state.json
```

Thì cùng thư mục đó, project còn dùng:

- `last-report.json`
- `last-plan.json`
- `last-apply.json`
- `last-sync.json`

## 3. Nội dung của `app-state.json`

State mặc định hiện có:

- `version`
- `roots`
- `targets`
- `integrations`
- `last_scan_at`
- `last_plan_at`
- `last_apply_at`
- `last_sync_at`
- `activity_log`

## 4. Vì sao report/plan/apply/sync tách file riêng

Thiết kế hiện tại không nhét mọi payload lớn vào `app-state.json`.
Thay vào đó:

- state file giữ metadata và cấu hình
- artifact file giữ snapshot lớn

Lợi ích:

- payload state gọn hơn
- mỗi artifact có thể được mở trực tiếp khi debug
- dashboard vẫn lấy được full payload qua `api_payload()`

## 5. Cách state được merge với default

`load_state()` không đọc file rồi dùng nguyên trạng.
Nó merge với default state để:

- bổ sung key mới khi schema mở rộng
- giữ backward compatibility ở mức cơ bản
- tránh crash nếu file state cũ thiếu field

Logic merge hiện xử lý riêng:

- `targets`
- `integrations`
- `radarr`
- `sonarr`
- `sync_options`

## 6. Quản lý roots

`add_root()` có hành vi:

- loại root cũ nếu path trùng
- thêm root mới
- sort theo `priority` giảm dần rồi đến path

Điều này giúp thứ tự roots ổn định khi hiển thị và khi scan.

`remove_root()` xóa root theo path đã resolve.

## 7. Lưu targets

Targets được lưu dưới dạng string path hoặc `null`:

- `movie_root`
- `series_root`
- `review_root`

Khi load lên, chúng được convert lại thành `Path | None`.

## 8. Lưu integrations

State store không tự validate logic provider.
Nó chỉ lưu payload integrations đã được normalize ở tầng web.

Payload integrations hiện có 3 phần:

- `radarr`
- `sonarr`
- `sync_options`

## 9. Lưu timestamps

Mỗi khi lưu artifact tương ứng, state store cập nhật mốc thời gian:

- save report -> `last_scan_at`
- save plan -> `last_plan_at`
- save apply result -> `last_apply_at`
- save sync result -> `last_sync_at`

## 10. Activity log

Activity log hiện có giới hạn:

```text
ACTIVITY_LOG_LIMIT = 200
```

Mỗi event mới được chèn lên đầu danh sách.
Nếu vượt limit thì các event cũ hơn sẽ bị cắt bớt.

## 11. Dạng của activity event

Một activity event hiện gồm:

- `id`
- `kind`
- `status`
- `message`
- `created_at`
- `details`

`id` hiện được tạo từ:

- loại event
- `time.time_ns()`

## 12. API payload tổng hợp

`api_payload()` là nơi dashboard lấy snapshot đầy đủ.
Payload trả về gồm:

- toàn bộ state cơ bản
- report gần nhất
- plan gần nhất
- apply_result gần nhất
- sync_result gần nhất

Điều này giúp frontend chỉ cần gọi một endpoint chính để render hầu hết màn hình.

## 13. Những điểm cần lưu ý khi thay đổi schema

- frontend `app.js` phụ thuộc vào tên key trong payload hiện tại
- nếu đổi tên file artifact hoặc key timestamps thì dashboard sẽ lệch
- nếu activity `details` thay đổi mạnh, màn hình Activity Log vẫn render được nhưng người đọc có thể mất ngữ cảnh cũ
