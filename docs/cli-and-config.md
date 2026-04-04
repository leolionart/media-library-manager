# CLI And Configuration

## 1. Entry point

CLI entry point:

```bash
media-library-manager
```

Code nằm ở:

- [cli.py](/Volumes/DATA/Coding Projects/media-library-manager/src/media_library_manager/cli.py)

## 2. Commands hiện có

### `scan`

Dùng để scan roots và tạo report JSON.

Ví dụ:

```bash
media-library-manager scan \
  --root /Volumes/Media/Movies \
  --root /Volumes/Media/Series \
  --output ./report.json
```

### `plan`

Build action plan từ report hoặc từ roots/config.

Ví dụ:

```bash
media-library-manager plan \
  --report ./report.json \
  --output ./plan.json
```

### `apply`

Apply plan theo dry-run hoặc execute.

Ví dụ:

```bash
media-library-manager apply \
  --plan ./plan.json \
  --execute \
  --prune-empty-dirs
```

### `serve`

Chạy dashboard server.

Ví dụ:

```bash
media-library-manager serve \
  --host 127.0.0.1 \
  --port 8766 \
  --state-file ./data/app-state.json
```

## 3. Config roots

CLI hỗ trợ:

- `--root`
- `--priority-root`
- `--config`

### `--root`

Format:

```text
--root /path/to/root
```

Default:

- `priority = 50`
- `kind = mixed`
- `label = tên thư mục cuối`

### `--priority-root`

Format:

```text
PRIORITY:PATH
```

Ví dụ:

```bash
--priority-root 100:/Volumes/Media/Movies
```

### `--config`

Config TOML vẫn được hỗ trợ.

Ví dụ:

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

## 4. Vai trò hiện tại của CLI

CLI vẫn hữu ích cho:

- batch scan / plan / apply
- automation
- server bootstrap bằng `serve`

Nhưng hướng phát triển chính hiện tại nằm ở dashboard runtime và SMB-native API.

## 5. Local development

Backend local:

```bash
HOST=127.0.0.1 PORT=8766 ./run-dashboard.sh
```

Frontend local:

```bash
cd frontend
npm install
npm run dev
```

Build frontend:

```bash
cd frontend
npm run build
```
