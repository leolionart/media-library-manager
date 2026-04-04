# Current Features

Tài liệu này liệt kê các tính năng đang có trong dự án theo đúng hành vi hiện tại của code.

## 1. Dashboard được chia thành 2 page

### Operations

Page này dùng cho:

- xem connected folders dưới dạng list chính
- thao tác từng row bằng action dropdown
- scan connected folders
- xem duplicate suggestions
- build action plan
- dry-run apply
- execute apply
- preview và execute manual folder move
- move folder contents vào folder đang được Radarr/Sonarr quản lý
- delete folder

### Settings

Page này dùng cho:

- quản lý connected folders
- quản lý SMB profiles
- cấu hình Radarr/Sonarr
- test integrations

## 2. Connected folders

Project làm việc trên các folder đã tồn tại và đã được connect vào app.

Mỗi connected folder hiện có:

- `path`
- `label`
- `priority`
- `kind`
- `connection_id`
- `connection_label`

`connection_id` và `connection_label` giúp gắn root đó với một SMB profile đã lưu.

## 3. SMB profiles

Project hiện hỗ trợ:

- lưu nhiều SMB host
- username/password riêng cho từng host
- share name và base path riêng
- test kết nối bằng `smbclient`

SMB profile hiện là lớp setup trong `Settings`, dùng để giữ connection context cho từng connected folder. Khi add folder, modal sẽ ưu tiên gợi ý mounted runtime path tương ứng thay vì bắt người dùng nhớ lại path thủ công.

## 4. Duplicate detection

Project phát hiện duplicate ở 2 mức:

- exact duplicate files
- media collisions, tức cùng movie hoặc cùng episode xuất hiện ở nhiều nơi

Kết quả được dùng để build action plan gồm:

- `move`
- `delete`
- `review`

## 5. Manual folder move

Project hiện có một luồng thao tác riêng để move cả folder từ vị trí A sang vị trí B.

Luồng này:

- nhận `source folder`
- nhận `destination parent folder`
- preview destination cuối cùng
- execute bằng `shutil.move`

Nó phục vụ use case cut/paste folder đơn giản mà không cần đi qua duplicate planner.

## 6. Move to Radarr / Sonarr

Project hiện có thêm luồng thao tác từ folder list:

- `Move To Radarr...`
- `Move To Sonarr...`

Luồng này:

- lấy source folder từ row đang thao tác
- tải danh sách item hiện có từ provider
- để người dùng chọn đúng movie hoặc series đã được quản lý
- move toàn bộ nội dung của source folder vào path đang được provider quản lý
- sau khi move thật, gọi refresh hoặc rescan provider

Nếu path đã là folder provider đang quản lý sẵn, app không đổi `path` của provider mà chỉ refresh lại.

## 7. Duplicate workflow

Hệ thống vẫn giữ engine duplicate workflow hiện có:

- `scan`
- `plan`
- `apply`

Điều này phù hợp cho nhu cầu:

- phát hiện trùng
- review suggestion trước khi xoá
- chuẩn hoá library layout

## 8. Radarr và Sonarr

Project vẫn giữ integration layer cho:

- Radarr
- Sonarr

Settings hiện có:

- `base_url`
- `api_key`
- `root_folder_path`
- sync options

Từ dashboard hiện có thể:

- save settings
- test connectivity
- chạy sync thủ công
- sync tự động sau `apply --execute`

## 9. State persistence

Dashboard lưu:

- connected folders
- SMB profiles
- integration settings
- report/plan/apply/sync snapshots
- activity log
- current job logs
