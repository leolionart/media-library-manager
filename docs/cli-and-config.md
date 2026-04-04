# CLI And Configuration

Tài liệu này giải thích cách CLI hiện tại hoạt động và cách dự án nạp cấu hình roots/targets.

## 1. Entry point

Project publish command:

```bash
media-library-manager
```

CLI được khai báo trong `pyproject.toml` và trỏ vào:

```python
media_library_manager.cli:main
```

## 2. Các lệnh hiện có

### `scan`

Mục đích:

- quét các root
- tạo scan report JSON

Tham số chính:

- `--output`
- `--config`
- `--root`
- `--priority-root`

### `plan`

Mục đích:

- đọc report có sẵn hoặc tự scan lại
- build action plan

Tham số chính:

- `--report`
- `--output`
- `--movie-root`
- `--series-root`
- `--review-root`
- `--delete-lower-quality`
- `--config`
- `--root`
- `--priority-root`

### `apply`

Mục đích:

- đọc plan JSON
- chạy dry-run hoặc execute

Tham số chính:

- `--plan`
- `--execute`
- `--prune-empty-dirs`

### `serve`

Mục đích:

- chạy dashboard HTTP cục bộ

Tham số chính:

- `--host`
- `--port`
- `--state-file`

Lưu ý:

- `serve` mặc định port `8765`
- `run-dashboard.sh` mặc định port `9988`

## 3. Hai cách khai báo root

CLI hiện hỗ trợ khai báo root theo 2 cách.

### `--root`

Ví dụ:

```bash
media-library-manager scan \
  --root /Volumes/Media/Movies \
  --root /Volumes/Media/Series \
  --output ./report.json
```

Mỗi root kiểu này sẽ được gán:

- `label = tên thư mục cuối`
- `priority = 50`
- `kind = mixed`

### `--priority-root`

Ví dụ:

```bash
media-library-manager scan \
  --priority-root 100:/Volumes/Media/Movies \
  --priority-root 60:/Volumes/Archive/Movies \
  --output ./report.json
```

Format là:

```text
PRIORITY:PATH
```

Kiểu này cho phép gán priority rõ ràng cho từng root.

## 4. Nạp cấu hình từ file TOML

Project có thể đọc file TOML bằng `load_config()`.

Schema hiện tại:

```toml
[[roots]]
path = "/Volumes/MediaPool/Movies"
label = "Primary Movies"
priority = 100
kind = "movie"

[targets]
movie_root = "/Volumes/MediaPool/Movies"
series_root = "/Volumes/MediaPool/Series"
review_root = "/Volumes/MediaPool/_review"
```

Quy tắc default:

- `label` mặc định là tên thư mục cuối
- `priority` mặc định là `50`
- `kind` mặc định là `mixed`

## 5. Cách CLI resolve roots và targets

Hàm `resolve_roots_and_targets()` hiện hoạt động như sau:

1. nếu có `--config` thì load roots và targets từ TOML
2. nếu có `--root` hoặc `--priority-root` thì tạo roots từ CLI
3. nếu CLI có roots thì dùng roots từ CLI
4. nếu CLI không có roots thì fallback về roots từ config
5. nếu cuối cùng không có root nào thì exit với lỗi

Điều này có nghĩa:

- CLI roots override config roots
- config targets vẫn có thể được dùng làm base
- `plan` sau đó merge target từ config với target override truyền qua CLI

## 6. Merge targets trong lệnh `plan`

`plan` dùng logic:

- target truyền qua CLI sẽ override target từ config
- target nào không truyền thì giữ giá trị từ config

Điều này hữu ích khi:

- dùng một file TOML cố định
- nhưng tạm thời muốn override một target cho một lần chạy

## 7. Output của từng lệnh

### `scan`

Ghi ra:

- file report JSON
- summary trên stdout

### `plan`

Ghi ra:

- file plan JSON
- summary trên stdout

### `apply`

Không ghi file riêng qua CLI, nhưng in:

- summary trên stdout

Trong dashboard mode, kết quả apply còn được lưu vào state store.

## 8. Một số hành vi cần lưu ý

- `plan` có thể chạy mà không cần `scan` trước nếu bạn truyền roots/config thay vì `--report`
- `apply` không tự validate lại logic scan/planner, nó tin rằng `plan.json` đã đúng
- CLI hiện không có command riêng để test integrations; phần này nằm ở dashboard API
