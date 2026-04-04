# Scanning And Detection Logic

## 1. Scan scope

Scan hiện làm việc trên tất cả roots đã connect trong state.

Root có thể là:

- local filesystem
- SMB storage URI

## 2. Storage backend

Scan không còn phụ thuộc tuyệt đối vào `Path.rglob`.

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

## 6. Current job logging

Scan dashboard mode ghi log theo các event:

- `root_started`
- `root_completed`
- `scan_completed`

Những log này được lưu trong `current_job.logs`.

## 7. Cancel behavior

`scan_roots()` hiện nhận `should_cancel`.

Engine check cancel:

- trước mỗi root
- trong lúc iterate từng file video

Nếu cancel được request:

- scan raise error kiểu cancel
- backend finish job với `status = cancelled`

## 8. SMB caveat

Cancel scan SMB là cooperative, không phải hard kill.

Nếu backend đang ở một lệnh `smbclient` dài, cancel flag sẽ được thấy ở bước an toàn kế tiếp chứ không ngắt syscall tức thì.
