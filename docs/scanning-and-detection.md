# Scanning And Detection Logic

Tài liệu này mô tả logic scan library và cách hệ thống phát hiện duplicate hiện tại.

## 1. Phạm vi file được quét

Scanner đi qua từng root bằng `Path.rglob("*")`.
Chỉ các file có extension video sau mới được index:

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

Những file không nằm trong danh sách này sẽ bị bỏ qua ở bước scan.

## 2. Tạo `MediaFile`

Mỗi file video sau khi scan sẽ được chuyển thành một `MediaFile`.
Một số field quan trọng:

- `path`
- `root_path`
- `root_label`
- `root_priority`
- `kind`
- `media_key`
- `canonical_name`
- `title`
- `year`
- `season`
- `episode`
- `size`
- `relative_path`
- `resolution`
- `source`
- `codec`
- `dynamic_range`
- `quality_rank`

## 3. Parse movie và series

### Bước 1: làm sạch tên

Scanner chuẩn hóa text bằng cách:

- thay `.` và `_` bằng khoảng trắng
- bỏ một số dấu ngoặc
- collapse multiple spaces

### Bước 2: kiểm tra episode pattern

Scanner tìm episode pattern trước.
Các pattern hiện hỗ trợ:

- `S01E02`
- `1x02`

Nếu match:

- `kind = series`
- title lấy từ phần text trước pattern hoặc từ tên thư mục cha
- `canonical_name = "<Title> - SXXEYY"`
- `media_key = "episode:<slug-title>:sXXeYY"`

### Bước 3: fallback sang movie

Nếu không parse được episode:

- `kind = movie`
- cố tìm year trong filename trước
- nếu không có year trong filename thì thử tìm trong thư mục cha
- `canonical_name = "<Title> (YYYY)"` nếu có year
- `media_key = "movie:<slug-title>:<year|unknown>"`

## 4. Loại bỏ noise words

Trong bước chuẩn hóa title, scanner bỏ các token thường không thuộc tên media, ví dụ:

- `2160p`
- `1080p`
- `bluray`
- `remux`
- `webdl`
- `webrip`
- `x264`
- `x265`
- `hevc`
- `hdr`
- `proper`
- `repack`

Mục tiêu là tránh việc metadata chất lượng chui vào title.

## 5. Tính quality rank

`quality_rank` hiện được cộng từ nhiều thành phần:

- resolution, ví dụ `2160`
- source rank
- codec rank
- dynamic range rank

### Source rank hiện tại

- `remux = 120`
- `bluray = 100`
- `bdrip = 80`
- `web-dl/webdl = 70`
- `webrip = 60`
- `hdtv = 40`
- `dvdrip = 30`

### Codec rank hiện tại

- `av1 = 40`
- `x265/hevc/h265 = 35`
- `x264/h264 = 20`

### Dynamic range rank hiện tại

- `dv/dolbyvision = 20`
- `hdr = 15`

## 6. Exact duplicate detection

Scanner phát hiện exact duplicates theo 2 tầng.

### Tầng 1: group theo size

Mọi `MediaFile` được gom theo `size`.
Nhóm nào chỉ có 1 file thì bỏ qua vì không thể là exact duplicate.

### Tầng 2: hash SHA-256

Với mỗi size group có từ 2 file trở lên:

- scanner tính `sha256`
- nhóm tiếp theo theo hash
- nhóm nào có từ 2 file trở lên thì trở thành exact duplicate group

Mỗi group exact duplicate lưu:

- `sha256`
- `size`
- `media_keys`
- `items`

## 7. Media collision detection

Scanner gom tất cả `MediaFile` theo `media_key`.
Bất kỳ key nào có từ 2 file trở lên đều trở thành một media collision group.

Mỗi group collision lưu:

- `media_key`
- `kind`
- `canonical_name`
- `items`

Các item trong group được sort giảm dần theo `score_tuple()`.

## 8. Quy tắc chọn keeper

Project chọn keeper bằng `max(item.score_tuple())`.

`score_tuple()` hiện là:

```python
(quality_rank, size, root_priority, -len(relative_path))
```

Ý nghĩa:

1. ưu tiên bản chất lượng cao hơn
2. nếu bằng nhau thì ưu tiên file lớn hơn
3. nếu vẫn bằng nhau thì ưu tiên root có priority cao hơn
4. nếu vẫn bằng nhau thì ưu tiên đường dẫn tương đối ngắn hơn

## 9. Sidecar file detection

Scanner còn có hàm `companion_files(path)` để tìm file đi kèm với cùng stem.
Các extension sidecar hiện hỗ trợ:

- `.srt`
- `.ass`
- `.ssa`
- `.sub`
- `.idx`
- `.nfo`
- `.jpg`
- `.jpeg`
- `.png`

Các file này không được index như media chính, nhưng sẽ được move/delete cùng file video khi apply.

## 10. Output của scan

`ScanReport.to_dict()` hiện trả về:

- `version`
- `roots`
- `summary`
- `files`
- `exact_duplicates`
- `media_collisions`

Phần `summary` gồm:

- `files`
- `exact_duplicate_groups`
- `media_collision_groups`

## 11. Hệ quả của heuristic hiện tại

Ưu điểm:

- nhanh
- không phụ thuộc API ngoài
- đủ tốt cho naming convention phổ biến

Giới hạn:

- title có thể parse sai nếu naming quá lạ
- phim không có year dễ bị gom sai theo `unknown`
- nhiều release đặc biệt có thể làm title hoặc quality metadata bị hiểu chưa đúng
