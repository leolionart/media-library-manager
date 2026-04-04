# Radarr And Sonarr Integrations

## 1. Vai trò hiện tại

Provider layer hiện dùng cho:

- test kết nối
- lấy danh sách movie hoặc series
- move vào provider-managed path
- refresh provider item
- sync sau apply

Nó không điều khiển scan engine.

## 2. Config hiện có

Mỗi provider có:

- `enabled`
- `base_url`
- `api_key`
- `root_folder_path`

Sync options:

- `sync_after_apply`
- `rescan_after_update`
- `create_root_folder_if_missing`

## 3. Reverse proxy / Cloudflare note

Provider client hiện gửi `User-Agent` browser-like ở backend.

Lý do:

- một số deployment qua reverse proxy hoặc Cloudflare chặn request API nếu user-agent trông như script mặc định

Điểm này đã được xác thực với:

- `https://movie.naai.studio/`
- `https://tv.naai.studio/`

## 4. Provider APIs đang dùng

### `GET /api/integrations/radarr/items`

Trả list movie hiện có.

### `GET /api/integrations/sonarr/items`

Trả list series hiện có.

### `POST /api/integrations/test`

Test connectivity.

### `POST /api/integrations`

Save settings.

### `POST /api/sync`

Manual sync.

## 5. Move into provider path

Luồng:

1. user chọn folder trong `Media Management`
2. frontend load item list từ provider
3. user chọn movie hoặc series đích
4. backend gọi `move_folder_contents()`
5. backend refresh provider item tương ứng

## 6. Sync after apply

Khi `apply` chạy với `execute=true`:

- backend có thể gọi `sync_after_apply()`
- sync result được lưu vào state
- UI có thể xem lại sync status từ state
