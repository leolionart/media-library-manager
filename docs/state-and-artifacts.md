# State And Artifacts

Tài liệu này mô tả cách project lưu state và các file JSON trung gian.

## 1. StateStore lưu những gì

`StateStore` hiện là nguồn sự thật cho dashboard.

Nó lưu:

- connected folders
- targets
- integrations
- SMB profiles
- managed folder metadata nếu có
- timestamps
- activity log
- current job

## 2. Các file được dùng

Nếu state file là:

```text
./data/app-state.json
```

thì artifact files là:

- `last-report.json`
- `last-plan.json`
- `last-apply.json`
- `last-sync.json`

## 3. Payload state hiện tại

State cơ bản hiện có:

- `version`
- `roots`
- `targets`
- `integrations`
- `lan_connections`
- `managed_folders`
- timestamps
- `activity_log`
- `current_job`

## 4. Connected folders trong state

Connected folder vẫn được lưu trong `roots`, nhưng nghĩa product hiện tại là:

- root scan
- root vận hành
- root thuộc page `Settings`

Mỗi item có thể mang metadata SMB:

- `connection_id`
- `connection_label`

## 5. API payload tổng hợp

`api_payload()` trả:

- state cơ bản
- `report`
- `plan`
- `apply_result`
- `sync_result`

Frontend dùng một payload này để render cả `Operations` lẫn `Settings`.

## 6. Activity log

Activity log hiện chứa event của:

- config
- lan
- folder
- scan
- plan
- apply
- integration

Giới hạn hiện tại:

```text
ACTIVITY_LOG_LIMIT = 200
```
