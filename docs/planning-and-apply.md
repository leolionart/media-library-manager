# Planning And Apply Logic

Tài liệu này mô tả hai nhóm thao tác filesystem hiện có:

1. duplicate workflow `scan -> plan -> apply`
2. manual folder move kiểu cut/paste

## 1. Duplicate workflow

Planner biến `ScanReport` thành plan JSON gồm:

- `move`
- `delete`
- `review`

`operations.apply_plan()` sẽ:

- skip action `review`
- move file bundle cho action `move`
- delete file bundle cho action `delete`

Dry-run vẫn là mặc định an toàn.

## 2. Apply execute

Khi `execute=true`:

- tạo destination parent nếu cần
- move/delete thật trên filesystem
- có thể prune thư mục rỗng nếu bật option

## 3. Manual folder move

Ngoài duplicate workflow, `operations.py` hiện có thêm `move_folder()`.

Luồng này nhận:

- `source` là một thư mục
- `destination_parent` là thư mục cha đích

Hành vi:

- preview nếu `execute=false`
- move thật bằng `shutil.move()` nếu `execute=true`

Kết quả trả về:

- `source`
- `destination_parent`
- `destination`
- `status`
- `operations`

## 4. Điều kiện lỗi của manual move

`move_folder()` trả lỗi nếu:

- source không tồn tại
- source không phải directory
- destination parent không tồn tại
- destination parent không phải directory
- destination cuối cùng đã tồn tại
- destination parent nằm bên trong source

## 5. Mối quan hệ giữa hai luồng

Duplicate workflow và manual move là hai bề mặt khác nhau:

- duplicate workflow dùng cho phát hiện và xử lý duplicate
- manual move dùng cho thao tác cut/paste folder trực tiếp

Chúng cùng nằm trong page `Operations`, nhưng không phụ thuộc lẫn nhau.

## 6. Move folder contents into provider path

`operations.py` hiện còn có `move_folder_contents()`.

Hàm này phục vụ use case:

- source là folder download
- destination là folder movie hoặc series đã được Radarr/Sonarr quản lý

Hành vi:

- preview danh sách item sẽ được move nếu `execute=false`
- move từng child entry của source vào destination nếu `execute=true`
- nếu source rỗng sau khi move thì xóa source folder

Backend `web.py` dùng hàm này trong endpoint `POST /api/folders/move-to-provider`.

## 7. Delete folder

`operations.py` hiện có `delete_folder()` cho action dropdown ở folder list.

Hành vi:

- preview nếu `execute=false`
- xóa recursive directory tree nếu `execute=true`
