# Planning And Apply Logic

## 1. Hai nhóm operation chính

Hiện có hai nhóm thao tác filesystem:

1. duplicate workflow: `scan -> plan -> apply`
2. manual operations: move folder, delete folder, move vào provider path

## 2. Plan

`planner.py` nhận `ScanReport` và build action plan gồm:

- `move`
- `delete`
- `review`

`review` chỉ là suggestion, không apply trực tiếp.

## 3. Apply

`operations.apply_plan()` hỗ trợ:

- preview (`execute=false`, trong UI thường gọi là `Preview`)
- execute
- prune empty dirs
- progress callback
- cancel callback

Trong dashboard mode, apply còn:

- ghi log vào `current_job`
- lưu `last-apply.json`
- có thể sync providers sau execute

## 4. Manual move

`move_folder()`:

- nhận `source`
- nhận `destination_parent`
- preview nếu `execute=false`
- move thật nếu `execute=true`

Hiện hỗ trợ:

- local path
- SMB storage path

## 5. Move into provider path

`move_folder_contents()` dùng khi:

- source là folder download
- destination là path movie/series đang được provider quản lý

Hành vi:

- preview hoặc execute
- move từng child entry vào destination
- thử remove source folder nếu rỗng

## 6. Delete folder

`delete_folder()`:

- preview nếu `execute=false`
- delete recursive nếu `execute=true`

## 7. Cancel behavior

`apply_plan()` hiện nhận `should_cancel`.

Nếu user đã request cancel:

- apply dừng trước action tiếp theo
- backend finish job với `status = cancelled`

## 8. Sync relation

Sau execute apply:

- nếu `sync_after_apply = true`
- backend gọi `sync_after_apply()`
- sync result được lưu vào state
