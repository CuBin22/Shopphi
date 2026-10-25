# Kết nối GHN cho Shopphi

## Cấu hình

1. Chạy `.venv\Scripts\python.exe manage.py migrate`.
2. Thêm vào `.env` rồi khởi động lại Django:

```dotenv
GHN_ENABLED=1
GHN_API_URL=https://dev-online-gateway.ghn.vn
GHN_TOKEN=token_staging_cua_ban
GHN_SHOP_ID=ma_kho_ghn_cua_ban
GHN_WEBHOOK_SECRET=chuoi_ngau_nhien_dai_do_ban_tu_dat
GHN_TIMEOUT=10
```

Không commit token/secret hoặc gửi vào chat. Có thể tạo secret bằng `.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"`.

3. Vào `/admin/catalog/shop/`, mở từng gian hàng và nhập **Shop ID GHN**. Kho phải thuộc tài khoản API của sàn. Địa chỉ lấy hàng dùng hồ sơ kho trên GHN. Chỉ quản trị viên gán kho; không tự gán chung một kho cho mọi gian hàng. `GHN_SHOP_ID` trong `.env` chỉ dùng tra địa chỉ; nếu trống, dùng kho đã gán đầu tiên.

   Nếu tính phí báo `SHOP_INFO_ERROR`, vào trang GHN thử nghiệm và cập nhật đầy đủ địa chỉ lấy hàng của kho. Token gọi được danh sách tỉnh/thành không có nghĩa là kho đã đủ thông tin để tính cước.
4. Người bán vào **Sản phẩm → Sửa**, nhập khối lượng đóng gói (gram) và dài/rộng/cao (cm) của mỗi biến thể. Không có số đo thì hệ thống chặn đặt hàng GHN.
5. Khách chọn địa chỉ, bấm **Tính phí GHN**, xem tổng tiền rồi **Đặt hàng**.
6. Người bán bấm **Xác nhận đơn** để tạo vận đơn. Đơn online phải thanh toán trước. Trạng thái vẫn Đã xác nhận cho đến khi GHN nhận hàng. Nút **Đồng bộ GHN** lấy trạng thái mới, dùng được ngay trên localhost.

`GHN_ENABLED=0` giữ phí cố định cho đơn mới. Đơn GHN cũ vẫn đồng bộ/hủy qua GHN. Không đổi môi trường khi còn đơn cần xử lý; hệ thống chặn gửi đơn staging sang production hoặc ngược lại.

## Webhook

Ở [GHN Developer Staging](https://developer.ghn.dev), vào menu tài khoản → **Cấu hình webhook → Order**:

- URL: `https://TEN-MIEN-CUA-BAN/van-chuyen/ghn/webhook/`, ví dụ dùng ngrok.
- Header tùy chỉnh: `X-GHN-Secret`, giá trị giống `GHN_WEBHOOK_SECRET`.
- Bật sự kiện trạng thái đơn, retry và timeout 30 giây (lớn hơn `GHN_TIMEOUT`).
- Với domain riêng, thêm domain vào `ALLOWED_HOSTS` và origin vào `CSRF_TRUSTED_ORIGINS` trong settings.

GHN không gọi được localhost trực tiếp. Ngoài nút Đồng bộ, có thể chạy:

```powershell
.venv\Scripts\python.exe manage.py sync_ghn
```

Server kiểm tra secret và gọi lại API GHN để xác minh mã vận đơn, kho, trạng thái và thời điểm. Callback cũ/lặp không ghi nhận thanh toán hoặc hoàn kho lần nữa.

## Quy tắc nghiệp vụ và giới hạn

- Cước tính riêng cho từng gian hàng, kiểm tra lại tại backend lúc đặt. Nếu phí đổi, khách phải kiểm tra lại tổng tiền.
- Người gửi trả phí GHN (`payment_type_id=1`). COD thu đúng tổng tiền gồm cước; đơn online thu COD bằng 0, tránh thu cước hai lần.
- Kiện hàng, địa chỉ và kho được lưu lúc đặt. Sửa sản phẩm/kho sau đó không đổi dữ liệu đã báo giá.
- Retry tạo vận đơn dùng cùng `client_order_code`, GHN trả mã cũ thay vì tạo trùng.
- Khi tạo vận đơn timeout, đơn không được hủy/hoàn kho đến khi người bán bấm xác nhận lại lấy được mã. Lỗi 4xx rõ ràng ở lần đầu cho phép hủy; nếu đã có lần timeout trước đó thì vẫn cần đối soát. Không xóa cờ chờ đối soát khi chưa kiểm tra trên GHN.
- Hủy đơn có vận đơn chỉ hoàn kho sau khi GHN xác nhận hủy.
- GHN giao thành công hoàn thành đơn và ghi nhận COD. Đơn GHN không tự hoàn thành sau 7 ngày.
- Hoàn hàng, thất lạc, hư hỏng được ghi nhận và báo người bán xử lý thực tế; không tự hoàn tiền/nhập lại hàng vào kho.
- Dùng danh mục ba cấp vì API tính phí yêu cầu quận/huyện và mã phường/xã. Chưa tích hợp địa chỉ mới hai cấp.
- Hỗ trợ một kiện nhẹ dưới 20 kg, mỗi cạnh ≤200 cm, khai giá ≤5 triệu đồng. Vượt giới hạn yêu cầu tách đơn.
- Ghép kiện: dài/rộng lớn nhất, cộng chiều cao theo số lượng. Số đo phải phù hợp thực tế; GHN có thể điều chỉnh cước sau khi cân đo, hệ thống không tự tăng tiền khách đã trả.
- Một token sàn với nhiều kho; chưa hỗ trợ token riêng của từng người bán.

## Kiểm thử

`.venv\Scripts\python.exe manage.py test shopping.tests_ghn --noinput`

Tests dùng PostgreSQL test database và HTTP giả lập, không tạo vận đơn bên ngoài. Sau khi cấu hình, thử một đơn staging qua checkout, xác nhận, xem mã trên GHN, đồng bộ rồi hủy.

Nguồn: [Tạo đơn](https://developer.ghn.vn/vi/docs/order/create), [Tính phí](https://developer.ghn.vn/vi/docs/order/calculate-fee), [Webhook](https://developer.ghn.vn/vi/docs/webhook/callback-order-status), [Hủy đơn](https://developer.ghn.vn/vi/docs/order/cancel).
