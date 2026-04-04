# Radarr And Sonarr Integrations

Tài liệu này mô tả logic tích hợp hiện tại với Radarr và Sonarr.

## 1. Vai trò trong product mới

Trong product shape hiện tại:

- `Settings` giữ cấu hình provider
- `Operations` mới là nơi chạy duplicate workflow

Điều này có nghĩa:

- integrations không lẫn vào folder onboarding
- integrations không quyết định duplicate logic
- integrations chỉ bổ trợ cho path sync sau apply hoặc sync thủ công

## 2. Cấu hình hiện có

Mỗi provider có:

- `enabled`
- `base_url`
- `api_key`
- `root_folder_path`

`sync_options` có:

- `sync_after_apply`
- `rescan_after_update`
- `create_root_folder_if_missing`

## 3. Test kết nối

Dashboard gọi `POST /api/integrations/test`.

Kết quả:

- `disabled` nếu provider tắt
- `success` nếu gọi được `/api/v3/system/status`
- `error` nếu lỗi network, config hoặc HTTP

## 4. Thời điểm sync chạy

### Tự động

Sau `apply` với `execute=true`, dashboard gọi `sync_after_apply()`.

### Thủ công

Người dùng có thể gọi `POST /api/sync` từ `Settings`.

## 5. Mối quan hệ với manual folder move

Manual folder move là một luồng độc lập trong `Operations`.

Hiện tại code có 2 nhánh:

- `POST /api/folders/move`
  move cả folder từ A sang destination parent B
  nhánh này không tự sync provider

- `POST /api/folders/move-to-provider`
  move nội dung của source folder vào path đang được provider quản lý
  nhánh này sẽ refresh provider sau khi move execute thành công

Điều này phản ánh đúng use case:

- nếu người dùng move vào đúng folder movie/series mà Radarr/Sonarr đang track
- provider path không đổi
- app chỉ cần refresh hoặc rescan để provider nhìn thấy nội dung mới

## 6. Khi nào app update path, khi nào chỉ refresh

### Chỉ refresh

Nếu destination là path đang được provider quản lý sẵn:

- app move nội dung vào folder đó
- app không đổi `movie.path` hoặc `series.path`
- app chỉ gọi refresh hoặc rescan

### Update path

Luồng update path hiện vẫn thuộc duplicate workflow `apply + sync_after_apply()`.
Khi action plan đã move media sang path mới, integration layer có thể cập nhật `path` và `rootFolderPath` trên provider.
