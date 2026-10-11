# Shopphi - sàn thương mại điện tử đa gian hàng (bản chạy thử)

Đề tài **HeThongTMDTDaGianHang**: Django + PostgreSQL, giao diện Django template + JavaScript thuần.
README này ghi lại toàn bộ quá trình làm, những gì **đã làm** và **chưa làm**.


## 0. Tiến độ (cập nhật bản v3)

**Đã làm xong:** toàn bộ chức năng ở mục 3, gồm thanh toán trực tuyến qua ZaloPay Sandbox (tạo đơn, callback, truy vấn, đối soát, hoàn tiền); 59 test tự động đạt trên SQLite.
**Chưa làm / chưa kiểm chứng:** gọi thử ZaloPay thật trên máy bạn; chạy test trên PostgreSQL; các mục "Chưa làm" ở mục 4 (ảnh sản phẩm, Celery/cron, xuất báo cáo, quên mật khẩu/OTP...). Việc đầu tiên: `python manage.py migrate` rồi `python manage.py test`.

## 1. Cách chạy (Windows PowerShell)

```powershell
cd Shopphi
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# PostgreSQL: mặc định DB "Shopphi", user postgres, localhost:5432 (xem Shopphi/settings.py).
# Đổi bằng biến môi trường nếu cần: DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
python manage.py migrate
python manage.py seed_demo --reset      # nạp dữ liệu mẫu (xóa dữ liệu đơn hàng cũ!)
python manage.py runserver
```

Mở http://127.0.0.1:8000/ . Chưa có database thì tạo trước (pgAdmin hoặc `CREATE DATABASE "Shopphi" ENCODING 'UTF8';`).
Nếu bạn đã chạy bản trước: chỉ cần `python manage.py migrate` (migration `catalog/0003` thêm bảng nhật ký quản trị, `shopping/0002` thêm hạn giữ kho và bảng giao dịch thanh toán; giữ nguyên dữ liệu cũ).
`seed_demo --reset` xóa toàn bộ sản phẩm, đơn hàng, giỏ, hội thoại và các tài khoản mẫu rồi nạp lại. Bỏ `--reset` nếu không muốn mất dữ liệu.

### Tài khoản mẫu (mật khẩu `demo12345`)

| Vai trò | Đăng nhập |
| --- | --- |
| Khách hàng | `khach1@shopphi.vn`, `khach2@shopphi.vn`, `khach3@shopphi.vn` |
| Người bán (chủ 5 gian hàng theo thứ tự) | `ban1@shopphi.vn` ... `ban5@shopphi.vn` |
| Quản trị viên | `admin` / `admin12345` |

Mã giảm giá mẫu: `CHAOSHOPPHI` (toàn sàn, -10% tối đa 50.000đ, đơn từ 200.000đ), `GIAM30K` (toàn sàn, -30.000đ, chỉ 3 lượt), `SONG50K` (gian hàng Sóng Audio, -50.000đ, đơn từ 500.000đ).

### Thanh toán ZaloPay Sandbox (bản v3 - mới)

Mặc định (`PAYMENT_PROVIDER=zalopay`) nút **Thanh toán ngay** gọi API ZaloPay `POST /v2/create`, rồi chuyển khách sang trang thanh toán ZaloPay.

```powershell
python manage.py migrate        # migration shopping/0003_zalopay: cột ZaloPay cho giao dịch + bảng hoàn tiền
python manage.py runserver
```

Cấu hình bằng biến môi trường (xem cuối `Shopphi/settings.py`):

| Biến | Ý nghĩa | Mặc định |
| --- | --- | --- |
| `PAYMENT_PROVIDER` | `zalopay` hoặc `sandbox` (cổng giả lập chạy offline) | `zalopay` |
| `ZALOPAY_APP_ID`, `ZALOPAY_KEY1`, `ZALOPAY_KEY2` | Thông tin merchant Sandbox của bạn | tài khoản DEMO công khai (app_id 2553) |
| `ZALOPAY_ENDPOINT` | Địa chỉ API | `https://sb-openapi.zalopay.vn` |
| `ZALOPAY_CALLBACK_URL` | URL **công khai https** để ZaloPay báo kết quả, dạng `https://xxx.ngrok-free.app/thanh-toan/zalopay/callback/` | trống |
| `ZALOPAY_REDIRECT_URL` | URL khách quay về | tự dựng `/thanh-toan/zalopay/ket-qua/` |
| `ZALOPAY_BANK_CODE` | trống = trang ZaloPay Gateway (QR, thẻ ATM, thẻ quốc tế); `zalopayapp` = mở app ZaloPay | trống |

Cách thử: đăng nhập `khach1` > đặt hàng chọn *Thanh toán trực tuyến (ZaloPay Sandbox)* > **Thanh toán ngay** > thanh toán trên trang ZaloPay (dùng tài khoản/thẻ thử của ZaloPay Sandbox, xem https://docs.zalopay.vn/) > ZaloPay chuyển về, hệ thống hỏi lại ZaloPay (`/v2/query`) và cập nhật đơn.
Chạy local không có URL công khai thì ZaloPay không gọi được callback; hệ thống vẫn chốt kết quả nhờ truy vấn khi khách quay về và nhờ `python manage.py process_timeouts --loop 60` (đối soát nền). Muốn nhận callback thật: chạy ngrok, đặt `ZALOPAY_CALLBACK_URL`, và nên đăng ký cùng URL đó cho app trong cổng merchant ZaloPay.
Hoàn tiền: đơn đã thanh toán qua ZaloPay bị hủy sẽ ở *Chờ hoàn tiền*; Admin vào **Kênh quản lý > Hoàn tiền** > *Hoàn tiền* để gọi `/v2/refund` (nếu ZaloPay báo đang xử lý, bấm lại sau ít phút để hỏi `/v2/query_refund`).
Kiểm thử không cần mạng: `python manage.py test shopping.tests_zalopay` (phản hồi ZaloPay được giả lập).

### Thử nhanh các chức năng mới (bản v2)
1. **Thanh toán cổng giả lập** (đặt `PAYMENT_PROVIDER=sandbox`): `khach1` đặt hàng, chọn *Cổng thanh toán trực tuyến (Sandbox)* > Đặt hàng > **Thanh toán ngay** > ở trang cổng chọn *Thanh toán thành công / thất bại / Hủy*. Đơn chuyển *Đã thanh toán* rồi `ban1` mới xác nhận được. Thử để quá 15 phút (hoặc chạy `python manage.py process_timeouts`) để thấy đơn tự hủy và hoàn kho. Mở lại trang cổng của giao dịch cũ rồi bấm *Thanh toán thành công* để thấy **Thanh toán muộn** (Chờ hoàn tiền); admin hoàn tiền mô phỏng tại **Kênh quản lý > Hoàn tiền**.
2. **Người bán quản lý sản phẩm**: `ban1` > Kênh quản lý > **Sản phẩm** > Thêm / Sửa / Ẩn-Hiện / Xóa (sản phẩm đã có đơn thì chỉ bị ẩn).
3. **Admin**: `admin` / `admin12345` > Kênh quản lý > *Duyệt / khóa gian hàng*, *Gỡ / khôi phục sản phẩm*, *Từ khóa gợi ý*, *Hoàn tiền*, *Nhật ký quản trị*.
4. **Đánh giá mô hình gợi ý**: `python manage.py evaluate_recsys --demo` (dữ liệu giả lập) hoặc `python manage.py evaluate_recsys --events D:/data/retailrocket/events.csv --k 10` (dữ liệu thật, tải events.csv từ Kaggle "Retail Rocket ecommerce dataset").
5. **Kiểm thử**: `python manage.py test` (có 2 tệp: `shopping/tests.py` bản cũ và `shopping/tests_v2.py` bản mới).

Khóa ký cổng Sandbox đọc từ biến môi trường `PAYMENT_SANDBOX_SECRET` (có giá trị mặc định cho chạy thử).

### Thử nhanh luồng đầy đủ
1. Đăng nhập `khach1`, thêm sản phẩm của 2 gian hàng vào giỏ, **Đặt hàng**, nhập `CHAOSHOPPHI`, bấm *Áp dụng mã* rồi *Đặt hàng* (tách thành 2 đơn).
2. Đăng nhập `ban1` (hoặc gian hàng tương ứng), **Kênh quản lý > Đơn hàng**: xác nhận, nhập đơn vị vận chuyển và mã vận đơn để chuyển Đang giao.
3. Quay lại `khach1`, **Đơn hàng > Đã nhận hàng**, rồi đánh giá sản phẩm.
4. `ban1` hoặc `admin`: **Thống kê** (doanh thu, đơn hủy, tồn kho).
5. Nút **Hỏi chatbot** ở góc phải màn hình và ở trang chi tiết sản phẩm.

Tác vụ theo hạn (tự chấp nhận yêu cầu hủy sau 24 giờ, tự hoàn thành đơn sau 7 ngày kể từ Đang giao) chạy lười khi mở trang đơn hàng; ngoài ra có thể chạy `python manage.py process_timeouts --loop 60`.

Chatbot: không có khóa API thì chạy chế độ **offline** (soạn câu trả lời từ dữ liệu trong DB). Có LLM thật thì đặt biến môi trường
`ANTHROPIC_API_KEY` (và tùy chọn `CHATBOT_MODEL`) trước khi chạy `runserver`. Khóa không nằm trong mã front-end.

## 2. Quá trình làm

1. **Đọc đầu vào.** `Shopphi.rar` thực tế chứa cả `.venv` (Django 5.2.18) và bản `catalog` đã dựng ở lần trước. Môi trường làm việc không có công cụ giải nén RAR, không có Django và không có mạng, nên tôi tự viết bộ giải nén RAR5 bằng Python (kiểm tra CRC từng file, khớp 100%) để lấy lại mã nguồn, và lấy Django từ chính `.venv` của bạn để chạy thử.
2. **Giữ nguyên** phần đã có: tìm kiếm, gợi ý từ khóa, gợi ý sản phẩm, log hành vi, từ điển từ khóa, `catalog/migrations/0001`, cấu hình DB trong `settings.py` (đọc thêm từ biến môi trường).
3. **Thêm 3 app mới**: `accounts`, `shopping`, `chatbot`; mở rộng `catalog` (gian hàng có chủ sở hữu, địa chỉ lấy hàng, lý do khóa).
4. **Chuyển giỏ hàng** từ session sang bảng PostgreSQL cho khách đã đăng nhập (khách vãng lai vẫn dùng session, được gộp vào giỏ khi đăng nhập).
5. **Kiểm thử bằng Django thật** (SQLite do không có PostgreSQL trong môi trường làm việc): 14 test, đều đạt. Chạy lại trên máy bạn: `python manage.py test` (cần quyền tạo database `test_Shopphi` trên PostgreSQL).
6. Sửa một lỗi phát hiện khi test: chatbot từng khớp nhầm sản phẩm qua tên danh mục; nay chỉ khớp theo tên, thương hiệu, thẻ.

7. **Bản v2** (lần làm tiếp theo): đọc lại README và làm các mục "chưa làm": thanh toán Sandbox, Người bán quản lý sản phẩm, Admin gỡ/khôi phục + nhật ký quản trị, xóa mềm sản phẩm, script đánh giá gợi ý trên Retail Rocket. Thêm `shopping/tests_v2.py` (kiểm thử cho các phần trên). Môi trường làm việc lần này cũng không có Django nên chưa chạy được test (xem mục 4).

8. **Bản v3 - tích hợp ZaloPay Sandbox thật** (lần làm này). Đọc "ZaloPay APIs Integration Document" (v2) và làm: `shopping/zalopay.py` (gọi `/v2/create`, `/v2/query`, `/v2/refund`, `/v2/query_refund`, ký MAC bằng key1, xác thực callback bằng key2); tách lõi `payments._apply` dùng chung cho cổng giả lập và ZaloPay; callback + trang quay về + đối soát nền; hoàn tiền qua API; migration `shopping/0003_zalopay`; `shopping/tests_zalopay.py` (17 test mới). Chạy toàn bộ **59 test đều đạt** trên SQLite (42 test cũ + 17 mới). Môi trường làm việc vẫn không có mạng nên chưa gọi được ZaloPay thật (xem mục 4).

## 3. Đã làm (khớp tài liệu)

| Chức năng | Tham chiếu | Ghi chú |
| --- | --- | --- |
| Đăng ký, đăng nhập, đăng xuất | UC01, UC02, FR01, QĐ1, QĐ2 | Email hoặc SĐT không trùng; mật khẩu tối thiểu 8 ký tự gồm chữ và số, lưu băm; sai 5 lần khóa 15 phút (lưu DB); phiên đăng nhập hết hạn sau 30 phút không hoạt động; gắn hành vi và hội thoại của phiên ẩn danh vào tài khoản |
| Phân quyền 3 vai trò | FR21, NFR03 | Khách hàng / Người bán / Quản trị viên; kiểm tra ở back-end; người bán chỉ thấy dữ liệu gian hàng của mình; người bán không mua hàng |
| Đăng ký gian hàng | UC12 | Trạng thái Chờ duyệt; Admin duyệt hoặc khóa trong trang `/admin/` (khóa/từ chối bắt buộc ghi lý do, có thông báo cho người bán) |
| Giỏ hàng lưu PostgreSQL | UC05 | Tồn kho khả dụng, cộng dồn, tự loại sản phẩm ngừng bán |
| Đặt hàng, tách đơn theo gian hàng | UC06, FR08, QĐ9 | Một giao dịch DB; khóa dòng tồn kho; trừ kho bằng UPDATE có điều kiện; đơn giá lưu cố định; tổng nhóm = tổng các đơn; COD |
| Mã giảm giá | UC14, FR06, QĐ7 | Mã toàn sàn (Admin) và mã gian hàng (Người bán); 1 mã toàn sàn mỗi lần đặt và 1 mã gian hàng mỗi đơn; phân bổ theo tỷ lệ tạm tính, làm tròn xuống, dư vào đơn lớn nhất; tăng lượt dùng an toàn khi đặt đồng thời; hoàn lượt khi hủy; lịch sử áp dụng (BM7) |
| Xử lý đơn của Người bán | UC15, FR09, QĐ10 | Chuyển tuần tự; mã vận đơn duy nhất theo đơn vị vận chuyển; chặn giao khi còn yêu cầu hủy; Hoàn thành do khách xác nhận hoặc tự động sau 7 ngày |
| Theo dõi đơn | UC08, FR16 | Danh sách theo nhóm đơn, chi tiết, nhật ký trạng thái, chỉ xem đơn của mình |
| Hủy đơn, hoàn kho | UC09, FR10, QĐ11 | Chờ xác nhận: hủy ngay. Đã xác nhận: gửi yêu cầu, Người bán chấp nhận hoặc từ chối (ghi lý do), tự chấp nhận sau 24 giờ. Người bán hủy phải có lý do. Hoàn kho, hoàn lượt mã, ghi nhật ký trong cùng giao dịch |
| Đánh giá sản phẩm | UC10, FR12, QĐ13 | Chỉ đơn Hoàn thành; 1-5 sao; một lần cho mỗi sản phẩm; hiện ở trang chi tiết kèm điểm trung bình |
| Chatbot AI | UC11, FR19, FR24, QĐ12 | Kiểm tra độ dài (300 ký tự) và tần suất (8 tin/phút); chuẩn hóa không dấu, tách từ, nhận diện ý định; lấy giá, tồn kho, thông số từ DB; che email, SĐT, số thẻ trước khi ghi log và gửi LLM; từ chối câu hỏi ngoài phạm vi hoặc thiếu dữ liệu; lỗi LLM thì báo thân thiện; **hội thoại lưu và nạp lại từ PostgreSQL** |
| Thống kê và báo cáo | UC19, FR15, QĐ16 | Đơn hoàn thành, doanh thu (tạm tính trừ giảm giá, không gồm phí vận chuyển, theo SQL v3), hủy thủ công và hủy tự động, tồn kho hiện tại; chặn kỳ chứa ngày tương lai; Admin xem toàn sàn hoặc từng gian hàng và từ khóa phổ biến |
| Thông báo trên website | FR25 | Đơn mới, đổi trạng thái, yêu cầu hủy, duyệt/khóa gian hàng |
| **Thanh toán trực tuyến Sandbox** (mới) | UC07, FR11, FR22, FR23, NFR02, NFR15 | Cổng giả lập có nhãn SANDBOX, không nhận thông tin thẻ; một giao dịch cho cả nhóm đơn; mỗi nhóm chỉ một giao dịch đang hiệu lực (ràng buộc duy nhất trong DB); giữ kho 15 phút tính từ lúc đặt, thanh toán lại không kéo dài hạn; kết quả cổng được ký HMAC-SHA256, đối chiếu chữ ký + số tiền + mã giao dịch + mã nhóm đơn; mỗi giao dịch chỉ cập nhật đơn một lần (kết quả trùng bị bỏ qua); quá hạn tự hủy giao dịch + đơn + hoàn kho; kết quả thành công đến muộn (đơn đã hủy, hết hạn, hoặc nhóm đã thanh toán bằng giao dịch khác) ghi **Thanh toán muộn** và chuyển Chờ hoàn tiền; hủy đơn chưa thanh toán làm giao dịch đang chờ hết hiệu lực; hoàn tiền mô phỏng do Admin hoàn tất |
| **Thanh toán ZaloPay Sandbox** (v3) | UC07, FR11, FR22, FR23, NFR02, NFR04, NFR10 | Tạo đơn `/v2/create` (`app_trans_id` = yymmdd giờ VN + mã giao dịch, `amount` = tổng các đơn còn hiệu lực chưa thanh toán của nhóm, `item` liệt kê từng đơn, `embed_data.redirecturl`, MAC HMAC-SHA256 key1); không gửi thông tin cá nhân (app_user = `user<id>`); **callback** `/thanh-toan/zalopay/callback/` xác thực MAC key2, đối chiếu app_id + mã giao dịch + số tiền, mỗi giao dịch chỉ cập nhật đơn một lần (trả `return_code` 1 / 2 trùng / -1 từ chối); **trang quay về** không tin tham số URL mà hỏi lại `/v2/query`; **đối soát** trước khi hủy vì hết hạn giữ kho (không hủy nhầm đơn khách đã trả tiền mà callback bị lỡ; trả tiền đúng hạn nhưng kết quả về trễ vẫn tính là đúng hạn nhờ `server_time`) và bằng `process_timeouts`; tạo đơn lỗi thì giao dịch về Thất bại để thanh toán lại; kết quả thành công đến sau khi giao dịch đã Thất bại/Hết hạn/Hết hiệu lực thì thành **Thanh toán muộn** (không nuốt tiền); **hoàn tiền** `/v2/refund` + `/v2/query_refund`, lưu `RefundRecord` trước khi gọi để không hoàn hai lần; đơn ghi nhớ giao dịch đã trả (`Order.payment_txn`); cổng giả lập vẫn dùng được (`PAYMENT_PROVIDER=sandbox`) |
| **Người bán quản lý sản phẩm** (v2) | UC13, FR04, BM5, QĐ5 | Thêm / sửa / ẩn-hiện / xóa; danh mục, thương hiệu, thẻ, mô tả, thông số; nhiều biến thể với giá (>0, đã gồm VAT) và tồn kho (>=0); chỉ khi gian hàng Hoạt động; chỉ thao tác sản phẩm của gian hàng mình (sản phẩm gian hàng khác trả 404); xóa sản phẩm đã có đơn chỉ ẩn (xóa mềm), chưa có đơn thì xóa hẳn; không xóa biến thể đã phát sinh đơn; sản phẩm bị gỡ thì Người bán không tự hiển thị lại; tìm kiếm / gợi ý từ khóa tự cập nhật số sản phẩm khớp |
| **Admin: duyệt, khóa, gỡ, khôi phục** (mới) | UC16, UC17, UC18, NFR09 | Giao diện riêng: duyệt / từ chối / khóa / mở khóa gian hàng theo đúng luồng trạng thái của SQL v3 (Từ chối -> Chờ duyệt do Người bán sửa và gửi lại); gỡ và khôi phục sản phẩm (khôi phục về trạng thái Ẩn); ẩn/hiện từ khóa; bắt buộc ghi lý do; thông báo cho Người bán; **nhật ký quản trị** (xem tại Kênh quản lý > Nhật ký quản trị, và cả khi thao tác trong `/admin/`) |
| **Đánh giá gợi ý trên Retail Rocket** (mới) | NFR07 | `evaluate_recsys`: chia theo thời gian, so sánh mô hình cosine của website với phương án dự phòng "phổ biến" bằng Precision@K, Recall@K, NDCG@K, HitRate@K |
| Admin Django | | Xem và sửa dữ liệu đơn hàng, mã giảm giá, hội thoại chatbot, đánh giá... để đối chiếu với PostgreSQL |

## 4. Chưa làm / hạn chế còn lại

- **Chưa chạy thử được mã mới** trong môi trường làm việc (không có Django, PostgreSQL, mạng). Mã mới đã qua kiểm tra cú pháp Python và đối chiếu thủ công với mã cũ, nhưng **chưa được chạy**; 2 file migration mới (`catalog/0003`, `shopping/0002`) viết tay. Việc cần làm đầu tiên trên máy bạn: `python manage.py migrate`, `python manage.py test`. Nếu có lỗi, gửi lại nguyên văn thông báo lỗi để sửa. Nếu `makemigrations` báo còn thay đổi, chạy `python manage.py makemigrations` rồi `migrate` (an toàn, chỉ khác mô tả).
- Chưa chạy `evaluate_recsys` trên dữ liệu Retail Rocket thật (không có mạng để tải); mới chạy thử trên dữ liệu giả lập. Bạn cần tải `events.csv` từ Kaggle và chạy lệnh để lấy số liệu cho báo cáo. Khi vận hành, website vẫn dùng log hành vi của chính nó.
- **Chưa gọi thử được ZaloPay thật** (môi trường làm việc không có mạng): toàn bộ test dùng phản hồi giả lập, riêng lớp HTTP đã kiểm tra với server cục bộ. Việc cần làm đầu tiên trên máy bạn: `migrate`, `python manage.py test`, rồi đặt hàng thử qua ZaloPay Sandbox. Nếu ZaloPay trả lỗi (ví dụ `-53 HMAC_INVALID`, `-402`), gửi lại nguyên văn thông báo để sửa.
- Cần bạn đối chiếu với tài liệu/cổng merchant ZaloPay: (1) `ZALOPAY_KEY2` mặc định của app demo 2553 do tôi nhớ lại, **chưa kiểm chứng**, hãy dùng khóa của merchant Sandbox của bạn; (2) tên tham số ZaloPay thêm vào URL quay về (code đọc `apptransid`, nhưng không tin các tham số khác nên sai tên thì chỉ mất bước tự chốt, đối soát nền vẫn chốt được); (3) tài liệu ghi `return_code` khác 1/2 trong phản hồi callback là "không gọi lại", code trả `0` cho lỗi hệ thống tạm thời, hãy kiểm tra hành vi gọi lại thực tế.
- Đơn ZaloPay có hiệu lực tối đa 15 phút kể từ lúc tạo, còn hạn giữ kho tính từ lúc đặt hàng, nên khách có thể trả tiền sau khi đơn đã bị hủy vì quá hạn; trường hợp này đã được xử lý bằng Thanh toán muộn + hoàn tiền, không mất tiền. Chưa dùng tham số rút ngắn hạn đơn ZaloPay cho khớp hạn giữ kho.
- Hoàn tiền một phần của một giao dịch trả cho nhiều đơn dựa trên việc ZaloPay cho phép hoàn từng phần; chưa kiểm chứng trên Sandbox. Đơn dùng khuyến mãi của ZaloPay có thể bắt buộc hoàn toàn bộ (theo tài liệu).
- Chưa có giao diện admin xem danh sách `RefundRecord` riêng (xem được trong `/admin/` nếu đăng ký; hiện chỉ hiển thị trạng thái qua nút Hoàn tiền).
- Hết hạn giữ kho và các tác vụ theo hạn vẫn chạy "lười" khi mở trang đơn hàng / kênh quản lý, hoặc bằng `python manage.py process_timeouts --loop 60` (chưa dùng Celery/cron).
- Sản phẩm chưa có tải **hình ảnh** (tài liệu chưa quy định giới hạn ảnh, mục Open Issues UC13).
- Ngoài phạm vi theo tài liệu (hướng mở rộng): quên mật khẩu, xác minh OTP, sửa/xóa đánh giá và kiểm duyệt bình luận, xuất báo cáo ra Excel/PDF, hồ sơ giấy tờ gian hàng, tính phí vận chuyển theo khu vực, tích hợp API đơn vị vận chuyển, hoàn tiền thật, giao hàng thất bại / trả hàng.
- Giao diện là Django template + JS thuần, không tách React; chưa chạy HTTPS (cấu hình khi triển khai).

## 5. Giá trị tạm chốt cho "Open Issues"

| Vấn đề | Giá trị tạm dùng | Nơi chỉnh |
| --- | --- | --- |
| Phí vận chuyển | cố định 30.000đ mỗi đơn | `shopping/services.py` (`SHIPPING_FEE`) |
| Ngưỡng tự chấp nhận hủy, tự hoàn thành | 24 giờ, 7 ngày | `shopping/services.py` |
| Hạn giữ kho thanh toán trực tuyến, khóa ký cổng giả lập, cấu hình ZaloPay | 15 phút; `PAYMENT_SANDBOX_SECRET`; `ZALOPAY_*`, `PAYMENT_PROVIDER` | `Shopphi/settings.py` |
| Giới hạn chatbot | 300 ký tự, 8 tin/phút, chờ LLM 15 giây | `chatbot/service.py` |
| Gợi ý từ khóa, gợi ý sản phẩm | như bản trước (tối đa 8, tần suất >= 3, tương đồng >= 0,6, đủ dữ liệu khi >= 3 sản phẩm) | `catalog/services.py` |

## 6. Cấu trúc

```
Shopphi/            cấu hình, urls
accounts/           hồ sơ và vai trò, đăng ký/đăng nhập, khóa đăng nhập, phiên hết hạn
catalog/            sản phẩm, tìm kiếm, gợi ý (bản trước) + cột mới cho gian hàng
shopping/           giỏ hàng, đặt hàng, mã giảm giá, hủy đơn, đánh giá, thống kê, kênh quản lý
                    payments.py (thanh toán: lõi chung, cổng giả lập, ZaloPay, hoàn tiền), zalopay.py (gọi API ZaloPay + ký MAC), moderation.py (duyệt/khóa/gỡ), product_views.py (Người bán quản lý sản phẩm),
                    admin_views.py (giao diện Quản trị viên), tests.py + tests_v2.py + tests_zalopay.py
chatbot/            hội thoại, che thông tin cá nhân, gọi LLM, API JSON
```
