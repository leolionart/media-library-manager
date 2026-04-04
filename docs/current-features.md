# Current Features

## 1. Frontend mới

Frontend hiện tại là React + Ant Design.

UI có 3 view:

- `Overview`
- `Operations`
- `Settings`

## 2. Connected roots

App làm việc trên các root đã connect vào state.

Mỗi root hiện có thể là:

- local path
- SMB storage root

Mỗi root có thể mang:

- `path`
- `label`
- `priority`
- `kind`
- `connection_id`
- `connection_label`
- `storage_uri`
- `share_name`

## 3. SMB profiles

App hiện hỗ trợ:

- nhiều SMB profiles
- test connection bằng `smbclient`
- browse host shares
- browse share folders
- add nhiều SMB roots

SMB hiện là first-class workflow, không phải chỉ là helper cho mounted path.

## 4. Folder inventory và tree

`Operations` hiện có hai dạng dữ liệu để render:

- inventory phẳng từ `GET /api/operations/folders`
- tree cha-con từ `GET /api/operations/folders/tree?depth=...`

Tree payload phục vụ UI expand/collapse.

## 5. Duplicate workflow

App vẫn có đầy đủ:

- `scan`
- `plan`
- `apply`

`scan` hỗ trợ local và SMB roots thông qua storage abstraction.

## 6. Manual filesystem operations

Hiện có:

- move folder
- delete folder
- move folder contents vào path của provider

## 7. Radarr / Sonarr

App hiện hỗ trợ:

- save provider settings
- test provider connectivity
- list provider items
- move vào provider path
- sync sau apply
- sync thủ công

## 8. Current job logs

Các job dài như scan, plan, apply hiện có:

- persisted `current_job`
- detailed `logs`
- `summary`
- `details`
- `cancel_requested`

Refresh trang vẫn thấy trạng thái job.

## 9. Cancel job

Backend hiện hỗ trợ:

- `POST /api/process/cancel`

Cancel là cooperative:

- state đổi sang `cancel_requested`
- log ghi cancel request
- job dừng ở safe point tiếp theo

## 10. Những gì đã bỏ khỏi UI mới

UI hiện tại không còn dùng:

- `Canonical Targets`
- `Managed SMB Folders`

Backend vẫn còn giữ field / API cũ liên quan, nhưng đó không còn là workflow UI chính.
