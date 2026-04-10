# Scanning And Detection Logic

## 1. Scan scope

Scan hiện làm việc trên tất cả roots đã connect trong state.

Các luồng scan chính (`duplicate scan`, `provider cleanup`, `empty-folder cleanup`, `provider path repair issue scan`) ưu tiên đọc từ `folder metadata cache` trước. Khi cache thiếu capability cần thiết hoặc version cũ, backend sẽ tự refresh folder index rồi retry.

Root có thể là:

- local filesystem
- SMB storage URI
- rclone remote via `storage_uri` (e.g. `rclone://remote/path`)

## 2. Storage backend

Scan không còn phụ thuộc tuyệt đối vào `Path.rglob`.

Với duplicate scan, storage backend live (`LocalPathScannerStorage` hoặc `StorageManagerScannerStorage`) hiện là fallback path khi cache metadata không khả dụng.

Hiện có hai mode:

- local scan qua `LocalPathScannerStorage`
- SMB-native scan qua `StorageManagerScannerStorage`

Điều này cho phép scan trực tiếp SMB roots mà không cần mount local làm workflow chính.

## 3. File types được index

Video extensions:

- `.mkv`
- `.mp4`
- `.avi`
- `.m4v`
- `.mov`
- `.wmv`
- `.mpg`
- `.mpeg`
- `.ts`
- `.m2ts`
- `.iso`

## 4. Duplicate detection

Hai lớp phát hiện:

- exact duplicate files
- media collisions

### Exact duplicates

Flow:

1. group theo `size`
2. tính `sha256`
3. group theo hash

### Media collisions

Group theo `media_key`.

## 5. Parsed metadata

Mỗi file sau scan tạo thành `MediaFile` với các field như:

- `kind`
- `media_key`
- `canonical_name`
- `title`
- `year`
- `season`
- `episode`
- `resolution`
- `source`
- `codec`
- `dynamic_range`
- `quality_rank`
- `storage_uri`
- `root_storage_uri`

## 6. Folder metadata cache capabilities

Folder index report hiện có `version = 3` và khai báo `capabilities` để các luồng scan kiểm tra trước khi dùng cache.

Các capability chính:

- `video_files`
- `has_any_file`
- `non_video_file_count`
- `child_folder_count`
- `normalized_name`

Nếu thiếu capability cần thiết, backend sẽ chuyển sang refresh index thay vì dùng dữ liệu cache cũ.

## 7. Current job logging

Scan dashboard mode ghi log theo các event:

- `root_started`
- `directory_scanned`
- `file_indexed`
- `root_completed`
- `scan_completed`

Những log này được lưu trong `current_job.logs`.

Với SMB hoặc rclone-backed roots, log trung gian này giúp thấy scan đang đi tới thư mục nào và đã index được bao nhiêu video files gần như liên tục, thay vì chỉ thấy lúc bắt đầu và kết thúc root.

## 8. Cancel behavior

`scan_roots()` hiện nhận `should_cancel`.

Engine check cancel:

- trước mỗi root
- trong lúc iterate từng file video

Nếu cancel được request:

- scan raise error kiểu cancel
- backend finish job với `status = cancelled`

## 9. SMB caveat

Cancel scan SMB là cooperative, không phải hard kill.

Nếu backend đang ở một lệnh `smbclient` dài, cancel flag sẽ được thấy ở bước an toàn kế tiếp chứ không ngắt syscall tức thì.

## 10. Retry and resume behavior

Các scan nặng hiện có 2 lớp phục hồi:

- auto-retry với backoff khi lỗi có dấu hiệu transient như timeout hoặc rate limit
- manual `wait`, `retry`, `resume` qua `current_job.available_actions`

Với duplicate scan, provider cleanup scan, empty-folder cleanup scan, và provider path repair scan, backend giữ checkpoint mức root hoặc provider đã hoàn tất gần nhất. `resume` sẽ tiếp tục từ root/provider kế tiếp thay vì bắt đầu lại toàn bộ lượt scan.

## 11. Empty duplicate folder cleanup matching

Luồng empty-folder cleanup không còn chỉ so top-level folder names.

Backend hiện index thư mục đệ quy trong mỗi root và match duplicate groups theo `relative path` media đã chuẩn hoá giữa các roots, ví dụ:

- `Movies/Dune (2021)` và `Movie/Dune (2021)`
- `Series/Dark` và `TV Series/Dark`

Cleanup scan cũng tính luôn cờ `has_video` và `has_any_file` trong cùng lượt walk, thay vì index xong rồi recurse lại từng group.

Với `Series`, cleanup scan còn build inventory episode theo từng folder duplicate. Nếu một folder có episode-set là tập con chặt của bản duplicate khác, hoặc đơn giản là ít episode hơn nhưng vẫn overlap rõ với bản còn lại, folder yếu hơn sẽ được đánh dấu candidate với reason `inferior-video-set` thay vì bị bỏ qua chỉ vì cả hai phía đều có video.

Khi scan remote lớn, engine bỏ qua các thư mục metadata/noise phổ biến như `trickplay`, `@eaDir`, `Subs`, `Trailers` để giảm số lệnh backend và tránh kẹt ở các nhánh rác.

Điều này giúp dọn duplicate dưới `Movies` hoặc `Series` mà không tạo false positive lớn từ các tên chung như `Extras` hoặc `Season 01` ở nhánh khác.
