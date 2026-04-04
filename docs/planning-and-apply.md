# Planning And Apply Logic

Tài liệu này giải thích cách hệ thống chuyển từ scan report sang action plan, rồi từ plan sang thay đổi thật trên filesystem.

## 1. Mục tiêu của planner

Planner biến một `ScanReport` thành plan JSON có thể:

- preview
- audit
- apply bằng dry-run hoặc execute

Planner không scan filesystem trực tiếp.
Nó làm việc trên dữ liệu đã được scanner cung cấp.

## 2. Các loại action

Project hiện có 3 loại action:

- `move`
- `delete`
- `review`

Ý nghĩa:

- `move`: chuyển keeper về canonical location
- `delete`: xóa bản dư thừa
- `review`: giữ lại để người vận hành tự xem xét

## 3. Chọn keeper

Trong cả exact duplicate group lẫn media collision group, planner dùng `choose_keeper()` để lấy item tốt nhất theo `score_tuple()`.

Điều này làm cho cùng một cơ chế xếp hạng được dùng xuyên suốt:

- ở scan report, item tốt hơn thường đứng trước
- ở plan, keeper được chọn bằng logic tương tự

## 4. Logic cho exact duplicates

Với mỗi exact duplicate group:

1. chọn keeper
2. tính canonical destination cho keeper nếu có target root phù hợp
3. nếu destination khác path hiện tại, tạo action `move`
4. với mọi item còn lại trong group, tạo action `delete`

Reason hiện dùng:

- `canonicalize_best_exact_duplicate`
- `exact_duplicate`

## 5. Logic cho media collisions

Với mỗi media collision group:

1. chọn keeper
2. nếu keeper chưa được xử lý ở bước exact duplicate và có canonical target thì tạo `move`
3. với item còn lại:
   nếu `delete_lower_quality = false` thì tạo `review`
   nếu `delete_lower_quality = true` thì tạo `delete`

Reason hiện dùng:

- `canonicalize_best_media`
- `manual_review_same_media`
- `lower_quality_duplicate`

## 6. `handled_sources`

Planner dùng tập `handled_sources` để tránh tạo action trùng cho cùng một file.

Điểm này quan trọng vì:

- một file có thể xuất hiện trong exact duplicate group
- đồng thời vẫn nằm trong media collision group

Nếu không có guard này, plan có thể tạo 2 action khác nhau cho cùng một source path.

## 7. Build path đích

### Movie destination

Nếu item là movie và có `movie_root`:

```text
<movie_root>/<Canonical Name>/<Canonical Name>.<ext>
```

### Series destination

Nếu item là series và có `series_root`:

```text
<series_root>/<Show>/<Season XX>/<Show - SXXEYY>.<ext>
```

### Review destination

Nếu item bị đánh dấu review và có `review_root`:

```text
<review_root>/<kind>/<Canonical Name>/<original filename>
```

Nếu không có `review_root` thì action `review` vẫn được tạo, nhưng `destination` sẽ là `null`.

## 8. Cấu trúc action

Mỗi action hiện lưu:

- `type`
- `source`
- `destination`
- `reason`
- `media_key`
- `root_path`
- `keep_path`
- `details`

`details` giữ metadata như:

- `canonical_name`
- `kind`
- `title`
- `year`
- `season`
- `episode`
- `target_root`
- keeper/candidate quality rank trong một số action collision

## 9. Output của planner

Plan JSON hiện có:

- `version`
- `summary`
- `actions`

`summary` đếm số action theo loại:

- `move`
- `delete`
- `review`

## 10. Apply: hành vi tổng quát

`operations.apply_plan()` duyệt tuần tự qua `plan["actions"]`.

Hành vi theo type:

- `review`: không thao tác, trả về `skipped`
- `move`: gọi `perform_move()`
- `delete`: gọi `perform_delete()`
- type lạ: trả về `error`

## 11. Dry-run và execute

### Dry-run

Nếu `execute = false`:

- không đổi filesystem
- chỉ trả về danh sách operation dự kiến

### Execute

Nếu `execute = true`:

- tạo thư mục đích nếu cần
- move hoặc delete file thật
- có thể prune thư mục rỗng nếu bật option

## 12. Logic move

`perform_move()` xử lý cả bundle:

- file video chính
- mọi sidecar file cùng stem

Mỗi item trong bundle được map sang destination tương ứng:

- file video đi đến `destination`
- sidecar đi đến `destination.with_suffix(item.suffix)`

### Nếu destination đã tồn tại

Hệ thống xử lý theo 2 nhánh:

- nếu file đích và file nguồn có cùng hash thì xóa file nguồn
- nếu khác nhau thì trả về `error` và dừng action đó

Điều này giúp tránh ghi đè mù lên file đã tồn tại.

## 13. Logic delete

`perform_delete()` cũng xử lý cả bundle:

- video chính
- sidecar files

Ở dry-run, nó chỉ trả về danh sách file sẽ bị xóa.
Ở execute, nó `unlink()` từng file nếu file đó tồn tại.

## 14. Prune thư mục rỗng

Nếu bật `prune_empty_dirs`:

- sau move/delete, hệ thống thử `rmdir()` dần các thư mục cha
- dừng lại khi gặp thư mục không rỗng
- hoặc khi chạm tới `root_path`

Điều này giúp cleanup cấu trúc thư mục cũ mà không xóa nhầm ra ngoài scan root.

## 15. Tóm tắt kết quả apply

`summarize_results()` hiện đếm số result theo status:

- `applied`
- `dry-run`
- `skipped`
- `error`

## 16. Những giới hạn cần biết

- apply tin rằng plan đầu vào đã đúng, nó không tái kiểm tra nghiệp vụ
- action `review` hiện chỉ được skip, không có cơ chế move sang `review_root` ở bước apply
- nếu plan lớn, apply chạy tuần tự và chưa có batch processing hay rollback transaction
