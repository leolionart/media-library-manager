# Radarr And Sonarr Integrations

Tài liệu này mô tả logic tích hợp hiện tại với Radarr và Sonarr.

## 1. Mục tiêu của integration layer

Project xử lý cleanup trên filesystem trước.
Sau khi file đã được move thành công, integration layer có nhiệm vụ đồng bộ lại path ở Radarr/Sonarr để hai hệ thống tiếp tục theo dõi library đúng vị trí mới.

Điều quan trọng:

- integrations không quyết định file nào nên move/delete
- integrations chỉ chạy sau khi có plan và kết quả apply

## 2. Cấu hình mặc định

Project có cấu hình mặc định cho:

- `radarr`
- `sonarr`
- `sync_options`

Mỗi provider hiện có:

- `enabled`
- `base_url`
- `api_key`
- `root_folder_path`

`sync_options` hiện có:

- `sync_after_apply`
- `rescan_after_update`
- `create_root_folder_if_missing`

## 3. Test kết nối

Dashboard hỗ trợ test kết nối bằng `POST /api/integrations/test`.

Logic:

- nếu provider bị disable thì trả `status = disabled`
- nếu enabled thì gọi `/api/v3/system/status`
- nếu lỗi HTTP/network/config thì trả `status = error`

## 4. Thời điểm sync được chạy

### Sync tự động

Khi gọi apply ở mode execute từ dashboard:

1. dashboard chạy `apply_plan()`
2. nếu execute thành công, dashboard gọi `sync_after_apply()`
3. kết quả sync được lưu vào `last-sync.json`

### Sync thủ công

Người dùng cũng có thể gọi `POST /api/sync`.

Điều kiện:

- phải có `plan`
- phải có `apply_result`

## 5. Điều kiện bỏ qua sync

Nếu `sync_after_apply = false` thì integration layer trả về trạng thái:

- `status = skipped`
- `reason = sync_after_apply_disabled`

## 6. Root folder management

Nếu `create_root_folder_if_missing = true`:

- Radarr client sẽ kiểm tra root folder đã tồn tại chưa
- Sonarr client cũng làm tương tự
- nếu thiếu thì gọi API tạo mới

Nếu bước này lỗi, sync flow dừng lại và trả `status = error`.

## 7. Action nào được sync

Integration layer hiện chỉ sync các action `move` đã thực sự được apply thành công.

Nó lấy:

- `plan["actions"]` loại `move`
- `apply_result["results"]` có `status = applied` và `type = move`

Các action `delete` hoặc `review` không được sync.

## 8. Cách xác định provider

Project xác định provider bằng `media_key`:

- key bắt đầu bằng `movie:` -> Radarr
- ngược lại -> Sonarr

Điều này có nghĩa:

- movie collision/move sẽ sync sang Radarr
- episode/series move sẽ sync sang Sonarr

## 9. Matching logic cho Radarr

Khi sync movie, project cố tìm movie trong Radarr theo thứ tự:

1. path parent của source hoặc destination
2. `title + year`

Nếu tìm thấy:

- cập nhật `movie["path"]` thành thư mục chứa file đích
- nếu có target root thì cập nhật `rootFolderPath`
- gọi update movie với `moveFiles=false`
- tùy option, gọi thêm `RefreshMovie`

Nếu không tìm thấy movie phù hợp:

- trả `status = error`
- message là `movie not found`

## 10. Matching logic cho Sonarr

Khi sync series, project cố tìm series theo thứ tự:

1. source hoặc destination nằm bên dưới path của series
2. title đã normalize

Nếu tìm thấy:

- tính lại series path
- cập nhật `series["path"]`
- nếu có target root thì cập nhật `rootFolderPath`
- gọi update series với `moveFiles=false`
- tùy option, gọi thêm `RefreshSeries`

### Cách tính series path

Nếu destination nằm bên dưới `target_root`:

- lấy thư mục show trực tiếp dưới root đó

Nếu không:

- nếu cha trực tiếp là `Season XX` thì lấy thư mục cha của season
- ngược lại lấy thư mục cha trực tiếp của destination

## 11. Provider client hiện tại

`JsonApiClient` ở `providers/base.py` đang phụ trách:

- build URL
- gửi GET/POST/PUT
- gắn header `X-Api-Key`
- parse JSON response
- chuyển lỗi HTTP/network thành `ProviderError`

Client cụ thể:

- `RadarrClient`
- `SonarrClient`

## 12. Kết quả sync

Kết quả sync hiện có:

- `status`
- `summary`
- `results`

`summary` đếm:

- `updated`
- `error`
- `skipped`

Mỗi result có thể mang:

- `provider`
- `source`
- `destination`
- `item_id`
- `path`
- `refresh`
- `message`

## 13. Những giới hạn hiện tại

- integration phụ thuộc vào matching heuristic theo path hoặc title
- nếu item trên Radarr/Sonarr không match được thì sync sẽ fail cho item đó
- project không tạo movie/series mới trên provider, chỉ update item đã tồn tại
- sync chỉ được gọi trong dashboard flow, CLI `apply` hiện không tự trigger integrations
- `moveFiles=false` nghĩa là Radarr/Sonarr không phải bên tự di chuyển file; filesystem đã được tool này xử lý trước
