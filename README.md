# Media Library Manager

`media-library-manager` là ứng dụng local để quản lý thư viện media nằm trên:

- ổ đĩa local
- SMB shares
- thư viện đã được Radarr hoặc Sonarr quản lý

Trọng tâm hiện tại của dự án là:

1. kết nối nhiều root SMB hoặc local vào app
2. duyệt folder theo dạng inventory và tree để thao tác
3. scan tìm duplicate
4. build plan và apply
5. move folder vào đúng path mà Radarr hoặc Sonarr đang quản lý

Ứng dụng không thay Radarr hoặc Sonarr. Nó là lớp điều phối filesystem và vận hành library.

## Current Product Shape

Frontend hiện tại là React + Ant Design, được build vào:

- [src/media_library_manager/static/app.js](/Volumes/DATA/Coding Projects/media-library-manager/src/media_library_manager/static/app.js)
- [src/media_library_manager/static/styles.css](/Volumes/DATA/Coding Projects/media-library-manager/src/media_library_manager/static/styles.css)

Backend là Python HTTP server, vừa serve static frontend vừa expose API nội bộ.

App hiện có 3 màn chính:

- `Overview`
- `Operations`
- `Settings`

### Overview

Màn tổng quan để xem:

- trạng thái runtime
- tóm tắt root đã connect
- duplicate summary
- trạng thái provider
- current job
- activity gần đây

### Operations

Màn vận hành chính:

- xem danh sách folder đã discover từ các root
- xem tree thư mục theo root
- chọn folder làm source hoặc destination
- move folder
- move vào Radarr hoặc Sonarr
- scan duplicate
- build plan
- dry-run apply
- execute apply
- xem current job logs
- cancel job đang chạy

### Settings

Màn cấu hình:

- quản lý connected roots
- quản lý SMB profiles
- cấu hình Radarr
- cấu hình Sonarr
- cấu hình sync options

Các khối `Canonical Targets` và `Managed SMB Folders` đã bị bỏ khỏi UI mới.

## SMB-Native Workflow

Luồng hiện tại không yêu cầu mount share vào OS như luồng chính.

Nguyên tắc:

- SMB profile lưu host, share, username, password
- root SMB được lưu bằng `storage_uri`
- backend truy cập trực tiếp qua `smbclient`
- `path` local pseudo chỉ dùng làm identity dễ đọc trong state/UI

Ví dụ root SMB:

```text
storage_uri = smb://Download/?connection_id=smb-1775287593611315000
path        = /smb/smb-1775287593611315000/Download
```

App hiện hỗ trợ:

- nhiều SMB profiles
- nhiều roots trên cùng một profile
- nhiều shares trên cùng một host
- inventory phẳng và tree cho SMB roots

## Radarr / Sonarr

App vẫn tích hợp Radarr và Sonarr như provider layer.

Use case chính:

- lấy danh sách movie hoặc series đang được provider quản lý
- move folder download vào path đã có sẵn của provider
- refresh lại provider sau khi move
- sync lại provider sau `apply execute`

Hiện tại app đã được xác nhận chạy với:

- `https://movie.naai.studio/`
- `https://tv.naai.studio/`

Backend provider client gửi `User-Agent` browser-like để tránh reverse proxy / Cloudflare chặn request API.

## Current Backend APIs

Các API chính đang dùng:

- `GET /api/state`
- `GET /api/process`
- `POST /api/process/cancel`
- `GET /api/operations/folders`
- `GET /api/operations/folders/tree?depth=...`
- `GET /api/smb/browse`
- `POST /api/roots`
- `POST /api/roots/bulk`
- `DELETE /api/roots?path=...`
- `POST /api/scan`
- `POST /api/plan`
- `POST /api/apply`
- `GET /api/integrations/radarr/items`
- `GET /api/integrations/sonarr/items`
- `POST /api/integrations`
- `POST /api/integrations/test`
- `POST /api/sync`

## Current Job Model

`current_job` được persist trong state, nên refresh vẫn thấy job đang chạy hoặc job vừa xong.

Mỗi job hiện có:

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

Các job dài như `scan`, `plan`, `apply` đều ghi log vào state.

Cancel hiện là cooperative:

- `POST /api/process/cancel`
- state chuyển `cancel_requested = true`
- job dừng ở safe point tiếp theo

## Local Run

Chạy backend local:

```bash
HOST=127.0.0.1 PORT=8766 ./run-dashboard.sh
```

Trong môi trường macOS hiện tại, cổng nên dùng là:

```text
http://127.0.0.1:8766
```

Không nên dùng `8765` nếu máy đang có app khác chiếm cổng.

## Frontend Development

Source frontend nằm trong:

- [frontend/](/Volumes/DATA/Coding Projects/media-library-manager/frontend)

Chạy dev frontend:

```bash
cd frontend
npm install
npm run dev
```

Build frontend vào static bundle của backend:

```bash
cd frontend
npm run build
```

## SMB Runtime Requirement

Local runtime cần có `smbclient`.

Ví dụ:

```bash
# macOS
brew install samba

# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y smbclient
```

## Docker

Project vẫn có thể chạy bằng Docker Compose.

Chuẩn bị:

```bash
cp .env.example .env
mkdir -p data
```

Chạy:

```bash
docker compose up -d
```

Mặc định mở:

```text
http://localhost:9988
```

## Verification

Kiểm tra backend:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile src/media_library_manager/*.py src/media_library_manager/providers/*.py src/media_library_manager/storage/*.py
```

Kiểm tra frontend:

```bash
cd frontend
npm run build
```
