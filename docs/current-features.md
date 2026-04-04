# Current Features

Tài liệu này liệt kê các tính năng đang có trong dự án, theo đúng hành vi hiện tại của code.

## 1. Quản lý thư viện media trên filesystem

Project làm việc trực tiếp với file và thư mục trên máy:

- quét nhiều root cùng lúc
- hỗ trợ local disk, external disk, NAS và share mạng đã mount
- xử lý movie, series hoặc root loại `mixed`
- ưu tiên root theo `priority`

Mỗi scan root hiện có các thuộc tính:

- `path`
- `label`
- `priority`
- `kind`

## 2. Phát hiện duplicate ở 2 mức

### Exact duplicate

Hệ thống xem nhiều file là trùng tuyệt đối khi:

1. có cùng dung lượng
2. có cùng SHA-256

Điểm này giúp tránh hash toàn bộ library từ đầu. Chỉ những file cùng size mới bị hash để xác nhận trùng.

### Media collision

Hệ thống cũng gom nhóm nhiều file đại diện cho cùng một movie hoặc cùng một episode dù nội dung file không giống byte-for-byte.

Ví dụ:

- cùng một phim nhưng một bản `1080p WEB-DL`, một bản `2160p REMUX`
- cùng một tập phim nhưng nằm ở hai ổ khác nhau

## 3. Parse tên media từ filename và thư mục

Project không dựa vào metadata online. Nó parse media identity từ tên file và tên thư mục cha.

Logic hiện tại nhận diện:

- movie theo `title + year`
- episode theo `show title + season + episode`

Các pattern episode hỗ trợ:

- `S02E03`
- `2x03`

Nếu parse được episode thì file được xem là `series`.
Nếu không parse được episode thì file được xem là `movie`.

## 4. Chấm điểm chất lượng file

Mỗi file video được gán một `quality_rank`.
Điểm này dùng để chọn bản nên giữ lại trong exact duplicate group hoặc media collision group.

Nguồn điểm hiện tại:

- resolution
- source tag
- codec tag
- dynamic range tag

Project đang nhận diện các tag phổ biến như:

- resolution: `480p`, `576p`, `720p`, `1080p`, `2160p`
- source: `remux`, `bluray`, `bdrip`, `web-dl`, `webdl`, `webrip`, `hdtv`, `dvdrip`
- codec: `av1`, `x265`, `hevc`, `h265`, `x264`, `h264`
- dynamic range: `dolbyvision`, `dv`, `hdr`

## 5. Xây canonical library layout

Project có thể chuẩn hóa file về root đích nếu đã cấu hình target:

- movie đi về `movie_root`
- series đi về `series_root`
- item cần review có thể đi về `review_root`

Mục tiêu là gom library về cấu trúc ổn định thay vì để file nằm rải rác ở nhiều ổ.

## 6. Tạo action plan trước khi sửa dữ liệu thật

Project không sửa filesystem ngay trong bước scan hoặc plan.

Nó sinh plan JSON với 3 loại action:

- `move`
- `delete`
- `review`

Điều này cho phép:

- review trước khi chạy
- tích hợp với các bước kiểm tra ngoài hệ thống
- giữ lại audit trail rõ ràng

## 7. Dry-run mặc định

Bước apply mặc định chỉ mô phỏng:

- không đổi file thật
- vẫn trả về kết quả chi tiết
- phù hợp để kiểm tra plan

Chỉ khi thêm `--execute` hoặc gọi API apply với `execute=true` thì tool mới sửa filesystem thật.

## 8. Xử lý sidecar file

Khi move hoặc delete một file video, project còn xử lý thêm các file đi kèm có cùng stem:

- subtitle: `.srt`, `.ass`, `.ssa`, `.sub`, `.idx`
- metadata và artwork: `.nfo`, `.jpg`, `.jpeg`, `.png`

Điểm này quan trọng vì cleanup media library thường không chỉ có file video.

## 9. Web dashboard cục bộ

Project có dashboard web tích hợp sẵn để vận hành mà không cần chỉ dùng CLI.

Dashboard hiện hỗ trợ:

- quản lý roots
- lưu target roots
- xem mounted filesystem
- browse thư mục trên máy
- thêm root từ LAN Browser
- chạy scan
- build plan
- dry-run apply
- execute apply
- xem duplicate report
- xem action plan
- xem apply result
- xem activity log

## 10. Lưu state và lịch sử thao tác

Dashboard có state store trên JSON file để giữ:

- roots
- targets
- integration settings
- mốc thời gian scan/plan/apply/sync gần nhất
- report gần nhất
- plan gần nhất
- apply result gần nhất
- sync result gần nhất
- activity log

## 11. Tích hợp Radarr và Sonarr

Project hiện đã có tích hợp API cho Radarr/Sonarr.

Tính năng hiện có:

- bật/tắt riêng cho Radarr và Sonarr
- lưu `base_url`, `api_key`, `root_folder_path`
- test kết nối
- sync tự động sau `apply --execute` nếu option cho phép
- sync thủ công từ dashboard
- tạo root folder trên provider nếu chưa tồn tại và option cho phép
- trigger refresh sau khi cập nhật path

## 12. Cấu hình qua CLI hoặc file TOML

Project hỗ trợ 2 cách cấp cấu hình:

- truyền root/target trực tiếp qua CLI
- nạp từ file TOML

Điều này phù hợp cho cả:

- chạy tay cục bộ
- script hóa
- tích hợp vào workflow vận hành

## 13. Các giới hạn hiện tại

Một số giới hạn quan trọng cần nêu rõ:

- parse media là heuristic, không đảm bảo đúng với mọi naming convention
- không dùng metadata scraper hoặc database online để xác minh title
- chỉ xử lý những file có extension video đã được khai báo trong scanner
- dashboard chỉ browse được path mà máy đang chạy tool có quyền truy cập
- sync Radarr/Sonarr hiện tập trung vào cập nhật path và refresh sau khi filesystem đã được tool xử lý
