# 🤖 Noti.sale Real-Time Telegram Monitor (Hướng 2 - Không Cần Điện Thoại)

Dự án Python chạy cục bộ trên Windows (hoặc VPS Linux) tự động quét và bắt các bài **Post** và **Deal** mới nhất từ `noti.sale` ngay khi admin vừa đăng bài, bóc tách đầy đủ nội dung chi tiết, mã voucher, link Shopee và hình ảnh chất lượng cao để gửi sang Telegram Channel `@myhanhshopeehihi`.

---

## 🌟 Ưu Điểm Của Hướng 2

- **Hoàn toàn độc lập**: Không cần điện thoại Android, không cần MacroDroid, không lo hết pin, tắt ngầm hay wifi chập chờn.
- **Dữ liệu đầy đủ 100%**: Thay vì chỉ nhận banner 1-2 dòng tóm tắt như thông báo điện thoại, bot lấy được:
  - Tiêu đề đầy đủ
  - Toàn bộ nội dung bài viết
  - **Mã voucher cụ thể** (tự động phát hiện mã nhập tay)
  - **Link Shopee affiliate** gốc
  - Hình ảnh CDN chất lượng cao
  - Khung giờ / hạn dùng
- **Sequential Real-Time Polling**: Bắt theo số thứ tự ID liên tục (`+1`, `+2`), phát hiện bài mới trong vòng vài giây từ lúc xuất bản.
- **Chống trùng lặp tuyệt đối**: Tự động lưu mốc ID và danh sách đã gửi vào `state.json`.
- **Tự phục hồi & Dừng an toàn**: Hỗ trợ `Ctrl+C` lưu trạng thái, khi bật lại tiếp tục quét từ mốc ID dừng trước đó.

---

## 📁 Cấu Trúc Thư Mục

```text
Shopee noti/
├── .env                  # Cấu hình Token, Chat ID, chu kỳ quét
├── .env.example          # Mẫu cấu hình tham khảo
├── .gitignore            # Bỏ qua file rác, venv và cấu hình nhạy cảm
├── main.py               # Toàn bộ mã nguồn cào & giám sát tự động
├── requirements.txt      # Thư viện Python phụ thuộc
├── state.json            # Lưu mốc ID bài viết/deal gần nhất đã gửi
└── README.md             # Hướng dẫn chi tiết
```

---

## ⚙️ Cấu Hình File `.env`

```env
BOT_TOKEN=8913163560:AAGMG1RvOlYyav6VL_w_skmOOP1ZEyOQjVg
CHAT_ID=@myhanhshopeehihi
PRIVATE_CHAT_ID=8388775284
TEST_DEAL_ID=38298

# Cấu hình Real-time Monitor (Hướng 2)
POLL_INTERVAL_SECONDS=15    # Thời gian nghỉ giữa các lần quét (giây)
ENABLE_POST_MONITOR=True    # Quét bài viết mới (mẹo săn sale, mã voucher nhập tay)
ENABLE_DEAL_MONITOR=True    # Quét deal giảm giá mới
```

---

## 🚀 Các Lệnh Chạy Bot

Mở PowerShell tại thư mục dự án:

### 1. Chạy giám sát tự động liên tục (Mặc định cho Local / VPS)
```powershell
python main.py
```
- Bot sẽ quét kiểm tra mỗi `POLL_INTERVAL_SECONDS` (15s).
- Cứ khi nào có bài post hoặc deal mới xuất bản trên Nô Tì, bot sẽ tự động cào và gửi ngay lập tức sang Channel `@myhanhshopeehihi`.
- Bấm `Ctrl + C` bất cứ lúc nào để dừng an toàn.

### 2. Chạy thử nghiệm một số chu kỳ rồi tự dừng
```powershell
python main.py cycles 3
```
*(Chạy 3 chu kỳ quét rồi tự động dừng, thích hợp để test nhanh)*

### 3. Chạy đúng 1 chu kỳ duy nhất
```powershell
python main.py once
```

### 4. Test cào thủ công 1 bài viết hoặc deal cụ thể
- Test deal:
  ```powershell
  python main.py test 38298 deal
  ```
- Test post:
  ```powershell
  python main.py test 47449 post
  ```

---

## 📋 Mẫu Tin Nhắn Telegram Khi Có Bài Mới

```text
📢 THÔNG BÁO SĂN SALE

Đã lên quà Shopee VIP kìa.Nhận được 1 tháng Shopee VIP Free khi tặng bạn bè 2 tháng. Nghĩa là bạn bè

Đã lên quà Shopee VIP kìa.Nhận được 1 tháng Shopee VIP Free khi tặng bạn bè 2 tháng. Nghĩa là bạn bè nhập mã của bạn thì bạn bè sẽ được 2 tháng còn bạn sẽ được 1 tháng miễn phí

➡️ Link dẫn thẳng đến chổ ưu đãi -> https://shp.ee/pspvontb

Mọi người thử nhập mã của AD xem có được cộng dồn không => VIPR1L5Pu130wiwQjspc

🔗 https://noti.sale/post/47449

🎟 Mã: VIPR1L5Pu130wiwQjspc
```
*(Kèm ảnh banner chất lượng cao gửi bằng `sendPhoto`)*
