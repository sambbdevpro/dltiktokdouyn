# CLAUDE.md

## Mục tiêu dự án
Xây dựng công cụ tải nội dung từ **TikTok**, **Douyin**, và **YouTube** theo 2 chế độ:
- Thêm **từng link video** để tải riêng lẻ.
- Thêm **link kênh/user/channel** để quét và tải toàn bộ nội dung.

Đầu ra hỗ trợ:
- **Toàn bộ video** gốc.
- **File MP3** (trích âm thanh từ video).

---

## Phạm vi chức năng (MVP)
1. Nhập danh sách URL (video hoặc kênh).
2. Nhận diện nền tảng từ URL: TikTok / Douyin / YouTube.
3. Thu thập danh sách video từ kênh hoặc item đơn lẻ.
4. Tải video theo hàng đợi (queue).
5. Tuỳ chọn trích xuất MP3 từ video sau khi tải.
6. Lưu metadata cơ bản: title, uploader, platform, url, duration, publish_date.
7. Ghi log tiến trình + retry khi lỗi tạm thời.

---

## Yêu cầu kỹ thuật đề xuất
- Kiến trúc module:
  - `parsers/` (phân tích URL, nhận diện loại input)
  - `extractors/` (lấy danh sách video theo từng nền tảng)
  - `downloaders/` (tải video)
  - `transcoders/` (chuyển đổi MP3)
  - `storage/` (lưu file + metadata)
  - `queue/` (điều phối job)
- Hỗ trợ resume khi tiến trình bị gián đoạn.
- Tránh tải trùng (deduplicate theo platform + video_id).
- Cấu hình qua file `setting.local.json`.

---

## Quy ước output
- Cấu trúc thư mục:
  - `output/videos/{platform}/{channel_or_user}/...`
  - `output/audio/{platform}/{channel_or_user}/...`
  - `output/metadata/{platform}/...jsonl`
- Đặt tên file an toàn, tránh ký tự đặc biệt.
- Chuẩn hoá timestamp theo UTC.

---

## Bảo mật và tuân thủ
- Chỉ xử lý nội dung mà người dùng có quyền truy cập/hợp lệ.
- Tôn trọng điều khoản sử dụng của nền tảng.
- Không lưu cookie/token nhạy cảm vào log.
- Cho phép cấu hình giới hạn tốc độ (rate limit) để tránh bị chặn.

---

## Checklist triển khai gợi ý
- [ ] Chuẩn hoá schema input URL.
- [ ] Xây parser nhận diện URL TikTok/Douyin/YouTube.
- [ ] Xây extractor cho từng nền tảng.
- [ ] Xây downloader có retry + resume.
- [ ] Tích hợp convert MP3 (tuỳ chọn bật/tắt).
- [ ] Lưu metadata và trạng thái job.
- [ ] Viết test cho parser + pipeline tải cơ bản.
- [ ] Đóng gói CLI: `add`, `scan`, `download`, `export-mp3`.

---

## Hướng mở rộng sau MVP
- Lọc theo thời gian đăng / số lượng video gần nhất.
- Chế độ incremental sync (chỉ tải video mới).
- Web UI theo dõi queue và tiến độ.
- Hỗ trợ webhook/thông báo khi job hoàn tất.
