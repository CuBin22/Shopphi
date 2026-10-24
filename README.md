<<<<<<< HEAD
> Cập nhật: đã gỡ công cụ tạo dữ liệu/ảnh demo. Các ghi chú lịch sử bên dưới mô tả phiên bản cũ; dữ liệu hiện có không tự động bị xóa.

=======
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
# Shopphi - sàn thương mại điện tử đa gian hàng (bản chạy thử)

Đề tài **HeThongTMDTDaGianHang**: Django + PostgreSQL, giao diện Django template + JavaScript thuần.
README này ghi lại toàn bộ quá trình làm, những gì **đã làm** và **chưa làm**.


<<<<<<< HEAD
## 0. Tiến độ (cập nhật bản v6)

**Đã làm xong:** toàn bộ chức năng ở mục 3. Bản v6 hoàn thiện module **Khách hàng**: trang **chi tiết đơn hàng** viết lại (tiến trình, tiền, mã giảm giá, thanh toán, vận chuyển, yêu cầu hủy, nhật ký bằng tiếng Việt, đánh giá), **danh sách đơn** có tab trạng thái / tìm kiếm / phân trang / nút thanh toán, **mua lại**, trang **Đánh giá của tôi**, **thông báo** (đánh dấu đã đọc từng cái và tất cả, lọc chưa đọc, phân trang), trang **Tài khoản của tôi** (sửa hồ sơ, đổi mật khẩu), giỏ hàng chặn đặt khi vượt tồn kho, checkout lưu địa chỉ mặc định. Xem mục 1.3. **172 test tự động đạt** (122 cũ + 50 mới, SQLite). Bản v6.1 sửa lỗi treo sau thanh toán ZaloPay (mục 1.4).
**Chưa làm / chưa kiểm chứng:** xem giao diện bằng mắt trên trình duyệt (môi trường làm việc không có trình duyệt, v6 chỉ kiểm tra bằng test HTTP và duyệt thử với dữ liệu `seed_demo`); chạy test trên PostgreSQL; gọi thử ZaloPay thật; gửi email/SMS thật; các mục "Chưa làm" ở mục 4 (có mục riêng cho module Khách hàng). Việc đầu tiên khi cập nhật: `python manage.py migrate` (v6 **không** thêm migration) rồi `python manage.py test`.

## 0.3 Bản v6.4: thiết kế lại trang chi tiết sản phẩm

- **Trang chi tiết** (`catalog/templates/catalog/product.html`) bố cục lại theo phong cách storefront cam của dự án: thư viện ảnh có nút trước/sau, bộ đếm ảnh và điều khiển bằng phím mũi tên; khung giá; chọn biến thể (có nhãn *Hết hàng* bằng chữ); số lượng + tồn kho; nút *Thêm vào giỏ* / *Mua ngay*; mục *Chi tiết sản phẩm* (thông số + mô tả giữ xuống dòng); *Đánh giá* có điểm trung bình và phân bố theo sao; gợi ý sản phẩm.
- **Mobile**: thanh *Thêm vào giỏ / Mua ngay* cố định ở đáy màn hình, nút chatbot được đẩy lên trên thanh này.
- **Bỏ ghi chú Sandbox** ở chân trang (`base.html`), thay bằng dòng giới thiệu sàn. Các trang thanh toán và đơn hàng vẫn giữ nhãn Sandbox vì đó là một phần luồng thanh toán.
- `catalog/views.py`: thêm `rating_dist` (số đánh giá theo từng sao). `app.js`: thêm `initGallery`. Không có migration mới.

## 0.2 Bản v6.3: đăng ký bằng Gmail có xác nhận OTP, quên mật khẩu bằng OTP qua mail

- **Đăng ký** (`/dang-ky/`): chỉ nhận địa chỉ **Gmail** (`@gmail.com`). Bước 1 nhập họ tên, Gmail, vai trò, mật khẩu -> hệ thống gửi **mã OTP 6 chữ số** tới Gmail; **chưa tạo tài khoản**. Bước 2 (`/dang-ky/xac-nhan/`) nhập mã đúng thì mới tạo tài khoản rồi chuyển sang đăng nhập. Có nút *Gửi lại mã*.
- **Quên mật khẩu** (`/quen-mat-khau/`): nhập email đã đăng ký -> nhận OTP qua mail -> nhập mã + mật khẩu mới (đã có từ v4, giữ nguyên).
- Quy tắc OTP (dùng chung cho cả hai luồng, cấu hình trong `settings.py`): hiệu lực 10 phút, dùng một lần, sai quá 5 lần thì hủy mã, gửi lại cách nhau tối thiểu 60 giây, tối đa 5 mã/giờ; chỉ lưu băm HMAC của mã, không lưu mã gốc; mã mới hủy mã cũ.
- Mật khẩu được băm ngay từ bước 1 và giữ trong session phía server, không lưu mật khẩu gốc.
- Cần chạy `python manage.py migrate` (migration mới `accounts/0003_signup_otp`: bảng mã OTP đăng ký).
- Tài khoản cũ đăng ký bằng số điện thoại vẫn đăng nhập và quên mật khẩu (SMS) như trước; **đăng ký mới** chỉ còn bằng Gmail.

**Gửi mail thật qua Gmail** (nếu không đặt, mã OTP được IN RA cửa sổ chạy `runserver` để chạy thử):
1. Bật xác minh 2 bước cho tài khoản Gmail gửi thư, rồi tạo **Mật khẩu ứng dụng** (App password, 16 ký tự) tại https://myaccount.google.com/apppasswords .
2. Trước khi chạy server (PowerShell):
```powershell
$env:EMAIL_HOST_USER = "ten.gmail.cua.ban@gmail.com"
$env:EMAIL_HOST_PASSWORD = "xxxxxxxxxxxxxxxx"     # mật khẩu ứng dụng, KHÔNG phải mật khẩu đăng nhập Gmail
python manage.py runserver
```
**Cách đơn giản nhất:** sao chép `.env.example` thành `.env` (cùng thư mục với `manage.py`), điền `EMAIL_HOST_USER` và `EMAIL_HOST_PASSWORD`, rồi chạy server như bình thường: không cần gõ biến `$env:` mỗi lần. `.env` đã nằm trong `.gitignore`; biến đặt trong PowerShell vẫn được ưu tiên hơn `.env`.
Kiểm tra cấu hình bằng lệnh `python manage.py test_email ten@gmail.com` (in lỗi cụ thể: sai mật khẩu ứng dụng, bị ngắt kết nối...). Nếu báo **"Connection unexpectedly closed"**: tắt tính năng quét email/SSL của phần mềm diệt virus, đổi sang mạng khác (mạng trường/công ty hay chặn cổng 587), hoặc thử cổng 465: `$env:EMAIL_PORT="465"; $env:EMAIL_USE_SSL="1"`.
Không đưa mật khẩu ứng dụng vào mã nguồn. Test mới: `accounts/tests_signup.py` (13 test).

## 0.1 Bản v6.2: nút "Mua ngay" và sửa lỗi trang chi tiết đơn

- **Mua ngay** (trang chi tiết sản phẩm, cạnh nút *Thêm vào giỏ*): chọn biến thể + số lượng rồi bấm *Mua ngay* để sang thẳng trang **Đặt hàng** chỉ với sản phẩm đó (`POST /mua-ngay/` -> `/dat-hang/?mua-ngay=1`). Giỏ hàng hiện có **được giữ nguyên**, vẫn áp mã giảm giá, chọn COD / thanh toán trực tuyến (giữ kho 15 phút) như đặt hàng thường. Chưa đăng nhập thì chuyển tới trang đăng nhập; tài khoản Người bán bị chặn; hết hàng / vượt tồn kho / sản phẩm ngừng bán đều báo lỗi (kiểm tra lại lúc đặt). Nút tự vô hiệu khi biến thể hết hàng.
- **Sửa lỗi trang chi tiết đơn của Người bán** (`/quan-ly/don-hang/<id>/`): trang bị lỗi 500 khi nhật ký trạng thái có dòng do **hệ thống** tự ghi (tự hủy do hết hạn thanh toán, tự chấp nhận yêu cầu hủy, tự hoàn thành sau 7 ngày). Nhật ký nay hiển thị tiếng Việt như trang của khách, người thực hiện rỗng hiện là "Hệ thống".
- Test mới: `shopping/tests_buy_now.py` (15 test).
=======
## 0. Tiến độ (cập nhật bản v3)

**Đã làm xong:** toàn bộ chức năng ở mục 3, gồm thanh toán trực tuyến qua ZaloPay Sandbox (tạo đơn, callback, truy vấn, đối soát, hoàn tiền); 59 test tự động đạt trên SQLite.
**Chưa làm / chưa kiểm chứng:** gọi thử ZaloPay thật trên máy bạn; chạy test trên PostgreSQL; các mục "Chưa làm" ở mục 4 (ảnh sản phẩm, Celery/cron, xuất báo cáo, quên mật khẩu/OTP...). Việc đầu tiên: `python manage.py migrate` rồi `python manage.py test`.
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5

## 1. Cách chạy (Windows PowerShell)

```powershell
cd Shopphi
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# PostgreSQL: mặc định DB "Shopphi", user postgres, localhost:5432 (xem Shopphi/settings.py).
# Đổi bằng biến môi trường nếu cần: DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
python manage.py migrate
<<<<<<< HEAD
=======
python manage.py seed_demo --reset      # nạp dữ liệu mẫu (xóa dữ liệu đơn hàng cũ!)
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
python manage.py runserver
```

Mở http://127.0.0.1:8000/ . Chưa có database thì tạo trước (pgAdmin hoặc `CREATE DATABASE "Shopphi" ENCODING 'UTF8';`).
Nếu bạn đã chạy bản trước: chỉ cần `python manage.py migrate` (migration `catalog/0003` thêm bảng nhật ký quản trị, `shopping/0002` thêm hạn giữ kho và bảng giao dịch thanh toán; giữ nguyên dữ liệu cũ).
<<<<<<< HEAD

### Sử dụng dữ liệu thật

Đăng ký tài khoản và gian hàng của bạn, thêm sản phẩm và tải ảnh thật trong Kênh quản lý. Tạo quản trị viên bằng `python manage.py createsuperuser`. Các công cụ nạp dữ liệu và tạo ảnh demo đã được gỡ. Không chạy lệnh đặt lại dữ liệu khi sử dụng dữ liệu thật.

### 1.1 Bản v4: tất cả sản phẩm, quên mật khẩu OTP, sao lưu dữ liệu

**Tất cả sản phẩm.** Trang chủ có mục *Tất cả sản phẩm* (12 mới nhất + nút xem hết); mục **Tất cả** trên thanh danh mục và `/tim-kiem/` liệt kê **toàn bộ** sản phẩm đang bán, 24 sản phẩm một trang, giữ nguyên bộ lọc danh mục / giá / sắp xếp khi chuyển trang (trước đây bị cắt cứng ở 60 sản phẩm). Đổi trang không bị tính là một lần tìm kiếm mới trong log hành vi.

**Lưu và nạp dữ liệu PostgreSQL.** Toàn bộ dữ liệu (tài khoản, sản phẩm, đơn hàng, thanh toán, đánh giá...) vốn đã lưu trong PostgreSQL qua Django. Bản này thêm 3 lệnh:

```powershell
python manage.py check_db                           # kiểm tra kết nối PostgreSQL, migration còn thiếu, số dòng từng bảng
python manage.py export_data                        # sao lưu ra backups/shopphi_<ngày giờ>.json (UTF-8)
python manage.py export_data --out D:/sao_luu.json --no-logs     # bỏ log hành vi/hội thoại cho nhẹ
python manage.py import_data backups/shopphi_xxx.json            # nạp lại (ghi đè dòng trùng khóa chính)
python manage.py import_data D:/sao_luu.json --flush --yes       # XÓA sạch rồi nạp lại
```
Việc nạp chạy trong một giao dịch (lỗi thì không đổi gì), đặt lại sequence của PostgreSQL và làm mới số sản phẩm khớp của từ khóa. Ảnh sản phẩm nằm ở thư mục `media/products/`, cần sao chép riêng. Muốn sao lưu ở mức PostgreSQL: `pg_dump -U postgres -d Shopphi -F c -f shopphi.dump`, khôi phục bằng `pg_restore`.
Chưa có database thì tạo trước: `CREATE DATABASE "Shopphi" ENCODING 'UTF8';`, rồi `migrate`, rồi nhập dữ liệu thật qua Kênh quản lý hoặc `import_data`.

**Quên mật khẩu bằng OTP.** Đăng nhập > *Quên mật khẩu?* > nhập email hoặc số điện thoại đã đăng ký > nhận mã OTP 6 chữ số (email nếu nhập email, SMS nếu nhập số điện thoại) > nhập mã + mật khẩu mới.
Mặc định chưa cấu hình dịch vụ gửi nên **mã OTP được in ra cửa sổ đang chạy `runserver`** (email hiện cả nội dung thư, SMS hiện dòng `[SMS giả lập]`). Để gửi thật, đặt biến môi trường:

| Mục đích | Biến môi trường |
| --- | --- |
| Email thật (Gmail) | `EMAIL_HOST_USER` (địa chỉ Gmail), `EMAIL_HOST_PASSWORD` (**Mật khẩu ứng dụng** của Google, cần bật xác minh 2 bước), tùy chọn `EMAIL_HOST`, `EMAIL_PORT`, `DEFAULT_FROM_EMAIL` |
| SMS qua Twilio | `SMS_BACKEND=twilio`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` |
| SMS nhà cung cấp Việt Nam (eSMS, SpeedSMS...) | `SMS_BACKEND=ten_goi.ten_module.ham_gui` với hàm `ham_gui(phone, text)` tự viết gọi API của nhà cung cấp (xem `accounts/sms.py`) |
| Thông số OTP | `OTP_TTL_MINUTES` (10), `OTP_MAX_ATTEMPTS` (5), `OTP_RESEND_SECONDS` (60), `OTP_MAX_PER_HOUR` (5) |

Ví dụ PowerShell: `$env:EMAIL_HOST_USER="ban@gmail.com"; $env:EMAIL_HOST_PASSWORD="abcd efgh ijkl mnop"; python manage.py runserver`.
Bảo mật: mã sinh bằng `secrets`, chỉ lưu băm (HMAC + muối); dùng một lần; hết hạn sau 10 phút; sai 5 lần thì hủy mã; cách nhau 60 giây và tối đa 5 mã/giờ cho một tài khoản; trang không cho biết tài khoản có tồn tại hay không; đổi mật khẩu xong thì phiên cũ hết hiệu lực và khóa đăng nhập (sai 5 lần) được gỡ. Tài khoản `admin` tạo bằng `createsuperuser` không có email/SĐT đăng ký nên không dùng được chức năng này.

### 1.2 Bản v5: module Người bán và ảnh sản phẩm

Cập nhật: `pip install -r requirements.txt` (cần **Pillow**), `python manage.py migrate` (migration `catalog/0005`, `shopping/0004`).
**Ảnh sản phẩm:** tải ảnh thật qua Kênh quản lý; sao lưu thư mục `media/products/` cùng cơ sở dữ liệu.
**Hiển thị ảnh:** file lưu ở thư mục `media/products/`, được phục vụ tại `/media/...` khi chạy `runserver` với `DJANGO_DEBUG=1` (mặc định). Khi triển khai thật (DEBUG tắt) phải cấu hình web server (nginx/Apache) trỏ `/media/` tới thư mục `media/`; Django không tự phục vụ file này.

Đăng nhập tài khoản người bán của bạn > **Kênh quản lý**:

| Chức năng | Cách dùng |
| --- | --- |
| Ảnh sản phẩm | Sản phẩm > Thêm/Sửa: ảnh bìa + tối đa 5 ảnh phụ (tổng `PRODUCT_IMAGE_MAX_COUNT`=6), mỗi ảnh tối đa 3 MB (`PRODUCT_IMAGE_MAX_BYTES`), chỉ JPEG/PNG/WEBP, cạnh ngắn tối thiểu 200 px. Có xem trước khi chọn, xóa từng ảnh phụ, đặt ảnh phụ làm ảnh bìa. Hệ thống mở file bằng Pillow để xác định định dạng thật (đổi đuôi `.exe` thành `.png` vẫn bị từ chối), sửa chiều xoay theo EXIF, bỏ EXIF/GPS, thu nhỏ cạnh dài về 1200 px, lưu lại JPEG tên ngẫu nhiên; ảnh bị thay/xóa và ảnh của sản phẩm bị xóa được dọn khỏi đĩa |
| Danh sách sản phẩm | Ảnh nhỏ, lọc theo danh mục / trạng thái / mức tồn (còn, sắp hết `LOW_STOCK_THRESHOLD`=5, hết), tìm kiếm, phân trang 20 |
| Thêm nhiều biến thể | Nút *+ Thêm biến thể* ngay trong form (trước đây phải lưu rồi mở lại) |
| Kho nhanh | **Kho nhanh**: sửa giá và tồn nhiều biến thể rồi lưu một lần; tồn kho cộng trừ theo chênh lệch nên đơn khách vừa đặt không bị ghi đè; lọc sắp hết / hết hàng; có sai dòng nào thì không lưu dòng nào |
| Mã giảm giá | Sửa / Tạm ngưng / Bật lại / Xóa. Chưa dùng: sửa mọi thông tin hoặc xóa. Đã có lượt dùng: chỉ gia hạn ngày hết hạn và tăng số lượt, không xóa, dùng Tạm ngưng. Mã tạm ngưng không áp dụng cho đơn mới |
| Đơn hàng | Lọc theo mã đơn, tên/SĐT người nhận, mã vận đơn, thanh toán, khoảng ngày, trạng thái; phân trang; **In phiếu giao vận** (đơn Đã xác nhận / Đang giao; có số tiền COD cần thu hộ) |
| Đánh giá | **Đánh giá**: điểm trung bình, phân bố sao, lọc theo sao / sản phẩm (chỉ xem, chưa có trả lời) |
| Thông tin gian hàng | Sửa mô tả, địa chỉ lấy hàng, liên hệ (tên và loại hình đã duyệt nên không tự đổi) |
| Bảng điều khiển | Doanh thu hôm nay và 30 ngày, số sản phẩm, cảnh báo hết/sắp hết hàng, đơn chờ xác nhận quá 24 giờ, yêu cầu hủy, 5 sản phẩm bán chạy |

### 1.3 Bản v6: module Khách hàng

Cập nhật: chép đè các file mới/sửa (xem mục 6), **không cần migration**, không thêm thư viện. Đăng nhập tài khoản khách hàng của bạn.

| Chức năng | Địa chỉ | Chi tiết |
| --- | --- | --- |
| **Chi tiết đơn hàng** (UC08) | `/don-hang/<mã đơn>/` | Thanh tiến trình Chờ xác nhận > Đã xác nhận > Đang giao > Hoàn thành (đơn hủy hiện mốc Đã hủy màu đỏ) kèm thời điểm từng mốc; sản phẩm có ảnh nhỏ, liên kết tới trang sản phẩm (đã ngừng bán thì không liên kết); tạm tính, giảm giá gian hàng và toàn sàn kèm **mã giảm giá đã dùng**, phí vận chuyển, tổng; người nhận, địa chỉ, đơn vị vận chuyển, mã vận đơn; phương thức và trạng thái thanh toán, lịch sử giao dịch của nhóm đơn, số tiền cần thanh toán và hạn giữ kho, nút thanh toán; liên hệ gian hàng; các đơn khác cùng lần đặt; lịch sử yêu cầu hủy (chờ xử lý, chấp nhận, từ chối kèm lý do, tự chấp nhận sau 24 giờ); nhật ký trạng thái **bằng tiếng Việt** (trước đây hiện mã thô như `HOAN_THANH`); đánh giá ngay tại từng sản phẩm, đã đánh giá thì hiện sao và bình luận |
| **Danh sách đơn hàng** (UC08) | `/don-hang/` | Tab trạng thái có đếm số đơn (Tất cả, **Chờ thanh toán**, Chờ xác nhận, Đã xác nhận, Đang giao, Hoàn thành, Đã hủy); tìm theo mã đơn, mã nhóm đơn, tên sản phẩm, tên gian hàng; phân trang 10 nhóm đơn; ảnh nhỏ và tóm tắt sản phẩm; nút **Thanh toán** ngay trên danh sách khi nhóm đơn còn chờ thanh toán |
| **Mua lại** | nút trong chi tiết đơn (POST `/don-hang/<mã>/mua-lai/`) | Đưa sản phẩm của đơn cũ vào giỏ; không vượt tồn kho; bỏ qua sản phẩm đã ngừng bán hoặc hết hàng và báo rõ lý do |
| **Đánh giá của tôi** (UC10) | `/danh-gia-cua-toi/` | Tab *Chờ đánh giá* (sản phẩm của đơn Hoàn thành chưa đánh giá, gửi ngay tại trang) và *Đã đánh giá* (sao, bình luận, đơn gốc) |
| **Thông báo** (UC20, FR25) | `/thong-bao/` | **Không còn tự đánh dấu đã đọc khi mở trang**; bấm vào thông báo thì đánh dấu đã đọc và chuyển tới đơn liên quan; nút *Đánh dấu tất cả đã đọc*; lọc *Chưa đọc*; phân trang 20; chỉ đường dẫn nội bộ mới được chuyển tới; chỉ xem được thông báo của chính mình |
| **Tài khoản của tôi** | `/tai-khoan/` | Sửa họ tên, số điện thoại, địa chỉ nhận hàng mặc định (được điền sẵn khi đặt hàng). Tài khoản đăng ký bằng số điện thoại thì không đổi số ở đây (số là tên đăng nhập). Không cho dùng số đã thuộc tài khoản khác |
| **Đổi mật khẩu** | `/tai-khoan/doi-mat-khau/` | Phải nhập đúng mật khẩu hiện tại; mật khẩu mới theo QĐ1 (>= 8 ký tự, chữ và số) và khác mật khẩu cũ; giữ phiên hiện tại, các phiên khác bị đăng xuất |
| **Giỏ hàng** (UC05) | `/gio-hang/` | Nút *Đặt hàng* bị vô hiệu và có cảnh báo khi có dòng vượt tồn kho; thêm nút *Tiếp tục mua sắm* |
| **Đặt hàng** (UC06) | `/dat-hang/` | Ô *Lưu làm địa chỉ nhận hàng mặc định* (chỉ lưu khi đặt thành công; số điện thoại chỉ điền vào hồ sơ nếu hồ sơ chưa có) |
| Menu tài khoản | góc phải thanh đầu trang | Thêm *Tài khoản của tôi*, *Đánh giá của tôi* |

**Hướng dẫn kiểm thử tự động**

```powershell
python manage.py test shopping.tests_customer      # 39 test của v6 (chạy khoảng 1 phút)
python manage.py test                              # toàn bộ 172 test
```
Cần quyền tạo database `test_Shopphi` trên PostgreSQL. Nhóm test v6: `OrderDetailTests` (chi tiết, nhãn tiếng Việt, đơn hủy, nút thanh toán, lịch sử yêu cầu hủy, phân quyền), `MyOrdersTests` (tab, tìm, phân trang, không lộ đơn người khác), `ReorderTests`, `MyReviewsTests`, `NotificationTests` (kể cả chống chuyển hướng ra ngoài), `ProfileTests` (hồ sơ, đổi mật khẩu), `CartCheckoutTests`.

**Hướng dẫn kiểm thử thủ công** (sau `migrate` và thêm sản phẩm thật, chạy `python manage.py runserver`; dùng 2 cửa sổ trình duyệt, một cho `khach1`, một cho `ban1`)

1. *Đặt hàng*: `khach1` thêm sản phẩm của **2 gian hàng** vào giỏ > Đặt hàng, nhập `CHAOSHOPPHI`, tích *Lưu làm địa chỉ mặc định*, chọn thanh toán trực tuyến > Đặt hàng. Kỳ vọng: thành công, tách 2 đơn.
2. *Danh sách đơn*: vào **Đơn hàng của tôi**. Thấy nhóm đơn mới, nút *Thanh toán*; bấm tab *Chờ thanh toán* còn nhóm này; tab *Đã hủy* trống; gõ tên sản phẩm vào ô tìm thì chỉ còn đơn khớp.
3. *Chi tiết đơn*: bấm **Xem chi tiết**. Kiểm tra thanh tiến trình đứng ở *Chờ xác nhận*, dòng mã `CHAOSHOPPHI`, khối *Thanh toán* ghi số tiền cần trả cho cả nhóm và hạn giữ kho, khối *Đơn khác cùng lần đặt* dẫn sang đơn thứ hai.
4. *Thanh toán*: bấm *Thanh toán trực tuyến* (đặt `PAYMENT_PROVIDER=sandbox` nếu không có mạng; chọn *Thanh toán thành công*). Quay lại chi tiết đơn: trạng thái *Đã thanh toán*, có giao dịch trong *Lịch sử giao dịch*.
5. *Vòng đời đơn*: ở cửa sổ `ban1` vào Kênh quản lý > Đơn hàng, xác nhận rồi chuyển Đang giao (nhập `GHN` và một mã vận đơn). Tải lại chi tiết đơn của `khach1`: tiến trình tới *Đang giao*, hiện mã vận đơn và nút **Đã nhận hàng**; nhật ký ghi tên người thực hiện bằng tiếng Việt. Bấm *Đã nhận hàng*: đơn *Hoàn thành*, xuất hiện form đánh giá.
6. *Thông báo*: biểu tượng chuông có số chưa đọc. Mở **Thông báo**: các thông báo vẫn là *Mới* (không tự đọc). Bấm một thông báo: chuyển tới đơn, thông báo hết *Mới*. Bấm *Đánh dấu tất cả đã đọc*: số trên chuông biến mất.
7. *Đánh giá của tôi*: mở trang, thấy sản phẩm chờ đánh giá; chọn sao, gửi; sản phẩm chuyển sang tab *Đã đánh giá*. Thử gửi lần hai cho cùng sản phẩm: bị từ chối.
8. *Mua lại*: ở chi tiết đơn Hoàn thành bấm **Mua lại**. Giỏ có lại sản phẩm; thử ẩn sản phẩm bằng `ban1` rồi mua lại để thấy thông báo *đã ngừng bán*.
9. *Hủy đơn*: đặt đơn mới; ở *Chờ xác nhận* hủy được ngay (tiến trình hiện mốc *Đã hủy* đỏ, kho hoàn trả). Với đơn *Đã xác nhận*: gửi yêu cầu hủy, `ban1` từ chối kèm lý do; chi tiết đơn của khách hiện *Bị từ chối* và lý do.
10. *Tài khoản*: **Tài khoản của tôi** > đổi họ tên và địa chỉ, lưu; sang trang đặt hàng thấy địa chỉ mới được điền sẵn. **Đổi mật khẩu**: nhập sai mật khẩu hiện tại bị báo lỗi; đổi đúng thì vẫn đăng nhập, đăng nhập lại bằng mật khẩu mới được.
11. *Phân quyền*: đăng nhập `khach2`, mở `/don-hang/<mã đơn của khach1>/` phải ra 404; đăng nhập `ban1` mở `/don-hang/` phải ra 403; chưa đăng nhập mở `/don-hang/` phải chuyển tới trang đăng nhập.

**Hạn chế của v6 (module Khách hàng):** xem mục 4, nhóm "Khách hàng".

### 1.4 Bản v6.1: sửa lỗi "treo" sau khi thanh toán ZaloPay

**Triệu chứng:** thanh toán xong, trang ZaloPay (`qcgateway.zalopay.vn/pay/v2/result?...`) dừng ở dòng "Vui lòng không tắt trình duyệt cho đến khi giao dịch được xác nhận" và không chuyển về website. Trang này do ZaloPay Sandbox điều khiển, mã của dự án không can thiệp được việc nó có chuyển về hay không; Sandbox thỉnh thoảng xác nhận chậm. Vì vậy v6.1 làm cho website **không còn phụ thuộc vào việc ZaloPay chuyển về**:

| Thay đổi | Chi tiết |
| --- | --- |
| Mở ZaloPay ở **tab mới**, tab đặt hàng tự chờ | Nút *Thanh toán* (trang đặt hàng thành công, danh sách đơn, chi tiết đơn) mở ZaloPay ở tab mới. Tab cũ hiện khung "Đang chờ ZaloPay xác nhận", cứ 4 giây hỏi server (`/thanh-toan/<nhóm đơn>/trang-thai/`), server hỏi lại ZaloPay (`/v2/query`); thấy thanh toán xong thì **tự chuyển sang trang kết quả**. Có nút *Kiểm tra ngay* và *Thanh toán lại*. Chờ tối đa 16 phút |
| Tự đối soát khi mở trang đơn | Mở **Đơn hàng của tôi**, **Chi tiết đơn** hoặc trang đặt hàng thành công thì hệ thống chốt luôn các giao dịch ZaloPay còn chờ (giao dịch đã tạo hơn 3 giây) |
| Chặn "Thanh toán muộn" oan | Trước đây nếu đã trả tiền nhưng trang treo, khách bấm *Thanh toán* lại thì giao dịch cũ bị thay thế, rồi khi ZaloPay xác nhận nó thành *Thanh toán muộn* và phải hoàn tiền. Nay `create_payment` hỏi ZaloPay trước; đã trả thì chốt đơn là *Đã thanh toán* và báo "không còn đơn nào cần thanh toán" |

File: `shopping/payments.py` (`reconcile_user`, đối soát trong `create_payment`), `shopping/views.py` (`payment_status`), `catalog/static/catalog/js/pay.js` (mới), CSS `.paywait`, 3 template có form thanh toán, `shopping/tests_payment_wait.py` (11 test).

**Về số tiền hiển thị 20 000 VND ở trang Napas:** số tiền Shopphi gửi sang ZaloPay luôn là tổng các đơn còn hiệu lực chưa thanh toán của nhóm đơn (đã trừ giảm giá; ví dụ nhóm đơn 950.000 đ, kiểm tra trực tiếp trên dữ liệu mẫu thì `/v2/create` nhận `amount=950000` và các `item` cộng đúng bằng số đó; có test trong `tests_zalopay.py`). Trang `qcsimulatorbankconnector.zalopay.vn` là trang **giả lập ngân hàng Napas của ZaloPay**, nằm ngoài mã dự án. Tôi **chưa kiểm chứng được** trang đó có hiển thị cố định 20 000 hay không (môi trường làm việc không có mạng). Cách kiểm tra: (1) so số tiền ở trang ZaloPay Gateway đầu tiên (trang chọn phương thức), trang *Chi tiết đơn* ("Cần thanh toán ...") và trang Napas; (2) sau khi thanh toán, nếu ZaloPay ghi nhận số tiền khác với số tiền của giao dịch thì hệ thống **từ chối** kết quả ("Số tiền hoặc mã nhóm đơn không khớp"), còn nếu đơn chuyển *Đã thanh toán* thì số tiền ZaloPay ghi nhận đúng bằng tổng đơn. Nếu trang ZaloPay Gateway đầu tiên cũng hiện sai số, gửi ảnh chụp trang đó cùng tổng tiền trên trang *Chi tiết đơn*.

**Cách thử thủ công:** đặt hàng chọn thanh toán trực tuyến > *Thanh toán ngay* > ZaloPay mở ở tab mới, tab cũ hiện khung chờ > thanh toán (thẻ thử Napas của ZaloPay Sandbox) > dù tab ZaloPay có treo hay không, tab cũ tự sang trang đặt hàng thành công với trạng thái *Đã thanh toán* trong vài giây. Thử treo: đóng tab ZaloPay ngay sau khi nhập OTP, đợi vài giây hoặc bấm *Kiểm tra ngay*; hoặc mở *Đơn hàng của tôi*. Tự động: `python manage.py test shopping.tests_payment_wait`.

### Thanh toán ZaloPay Sandbox (bản v3)
=======
`seed_demo --reset` xóa toàn bộ sản phẩm, đơn hàng, giỏ, hội thoại và các tài khoản mẫu rồi nạp lại. Bỏ `--reset` nếu không muốn mất dữ liệu.

### Tài khoản mẫu (mật khẩu `demo12345`)

| Vai trò | Đăng nhập |
| --- | --- |
| Khách hàng | `khach1@shopphi.vn`, `khach2@shopphi.vn`, `khach3@shopphi.vn` |
| Người bán (chủ 5 gian hàng theo thứ tự) | `ban1@shopphi.vn` ... `ban5@shopphi.vn` |
| Quản trị viên | `admin` / `admin12345` |

Mã giảm giá mẫu: `CHAOSHOPPHI` (toàn sàn, -10% tối đa 50.000đ, đơn từ 200.000đ), `GIAM30K` (toàn sàn, -30.000đ, chỉ 3 lượt), `SONG50K` (gian hàng Sóng Audio, -50.000đ, đơn từ 500.000đ).

### Thanh toán ZaloPay Sandbox (bản v3 - mới)
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5

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

<<<<<<< HEAD
9. **Bản v4**: phân trang tất cả sản phẩm; quên mật khẩu OTP (`accounts/otp.py`, `accounts/sms.py`, migration `accounts/0002`, 22 test); lệnh `check_db` / `export_data` / `import_data` (11 test). Test viết xong phát hiện và sửa một lỗi: đếm số lần nhập sai OTP bị rollback do ném lỗi trong khối giao dịch (cho phép đoán mã vô hạn). Môi trường làm việc không có PostgreSQL và không có mạng nên chạy trên SQLite (cả trong bộ nhớ lẫn file thật cho vòng seed > export > import) và gửi mail dùng backend kiểm thử.

10. **Bản v5**: module Người bán và ảnh sản phẩm (`catalog/images.py`, `catalog/demo_images.py`, `shopping/vendor_views.py`, `shopping/product_views.py` viết lại; model `ProductImage`, trường `Coupon.is_active`; 30 test mới trong `shopping/tests_vendor.py`). Viết test phát hiện và sửa 2 lỗi: (1) tên ảnh bìa cũ được đọc sau khi form đã gán ảnh mới nên file cũ không bao giờ bị dọn (rác tích tụ trong `media/`); (2) danh sách sản phẩm phân trang không có thứ tự rõ ràng nên có thể trùng/mất sản phẩm giữa các trang. Môi trường làm việc vẫn không có PostgreSQL và không có trình duyệt, nên giao diện chỉ kiểm tra bằng test HTTP và đọc HTML, chưa nhìn thấy bằng mắt.

11. **Bản v6**: module Khách hàng. Đọc lại toàn bộ mã `shopping`, `accounts`, `catalog` và chạy 122 test nền (đạt) trước khi sửa. Nhận thấy trang chi tiết đơn đã có nhưng sơ sài (nhật ký hiện mã trạng thái thô, không có tiến trình, không thấy mã giảm giá / thanh toán / lịch sử yêu cầu hủy, đánh giá xong không thấy lại nội dung); danh sách đơn không lọc, không phân trang; thông báo tự đánh dấu đã đọc ngay khi mở trang nên không còn biết cái nào mới; chưa có trang hồ sơ, đổi mật khẩu, đánh giá của tôi, mua lại. Viết mới `shopping/customer_views.py` (thay `my_orders`, `order_detail`, `notifications` trong `shopping/views.py`), thêm `profile` / `change_password` vào `accounts`, 4 template mới + 3 template viết lại, bộ lọc nhãn tiếng Việt trong `shop_extras.py`, CSS cuối `app.css`, và `shopping/tests_customer.py` (39 test). Duyệt thử toàn bộ luồng với dữ liệu `seed_demo` trên SQLite thật (đặt hàng > thanh toán > giao > hoàn thành > đánh giá > mua lại): các trang đều trả 200 và đủ nội dung. Môi trường làm việc vẫn không có PostgreSQL, không có trình duyệt, không có mạng.

12. **Bản v6.1**: sửa lỗi treo sau thanh toán ZaloPay và kiểm tra số tiền gửi sang ZaloPay (xem mục 1.4). Chụp dữ liệu thật gửi tới `/v2/create` bằng đơn nhiều gian hàng có mã giảm giá để xác nhận số tiền đúng; thêm endpoint trạng thái thanh toán, JS chờ ở tab cũ, đối soát khi mở trang đơn, chặn Thanh toán muộn oan khi bấm thanh toán lại; 11 test mới, toàn bộ 172 test đạt.

=======
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
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
<<<<<<< HEAD
| Theo dõi đơn | UC08, FR16 | **v6:** danh sách có tab trạng thái, tìm kiếm, phân trang; chi tiết có tiến trình, mã giảm giá, thanh toán, vận chuyển, lịch sử yêu cầu hủy, nhật ký tiếng Việt; mua lại; chỉ xem đơn của mình (xem mục 1.3) |
=======
| Theo dõi đơn | UC08, FR16 | Danh sách theo nhóm đơn, chi tiết, nhật ký trạng thái, chỉ xem đơn của mình |
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
| Hủy đơn, hoàn kho | UC09, FR10, QĐ11 | Chờ xác nhận: hủy ngay. Đã xác nhận: gửi yêu cầu, Người bán chấp nhận hoặc từ chối (ghi lý do), tự chấp nhận sau 24 giờ. Người bán hủy phải có lý do. Hoàn kho, hoàn lượt mã, ghi nhật ký trong cùng giao dịch |
| Đánh giá sản phẩm | UC10, FR12, QĐ13 | Chỉ đơn Hoàn thành; 1-5 sao; một lần cho mỗi sản phẩm; hiện ở trang chi tiết kèm điểm trung bình |
| Chatbot AI | UC11, FR19, FR24, QĐ12 | Kiểm tra độ dài (300 ký tự) và tần suất (8 tin/phút); chuẩn hóa không dấu, tách từ, nhận diện ý định; lấy giá, tồn kho, thông số từ DB; che email, SĐT, số thẻ trước khi ghi log và gửi LLM; từ chối câu hỏi ngoài phạm vi hoặc thiếu dữ liệu; lỗi LLM thì báo thân thiện; **hội thoại lưu và nạp lại từ PostgreSQL** |
| Thống kê và báo cáo | UC19, FR15, QĐ16 | Đơn hoàn thành, doanh thu (tạm tính trừ giảm giá, không gồm phí vận chuyển, theo SQL v3), hủy thủ công và hủy tự động, tồn kho hiện tại; chặn kỳ chứa ngày tương lai; Admin xem toàn sàn hoặc từng gian hàng và từ khóa phổ biến |
<<<<<<< HEAD
| Thông báo trên website | UC20, FR25 | Đơn mới, đổi trạng thái, yêu cầu hủy, duyệt/khóa gian hàng. **v6:** đánh dấu đã đọc từng cái (bấm vào thông báo) và tất cả, lọc chưa đọc, phân trang |
| **Module Khách hàng hoàn thiện** (v6) | UC05, UC06, UC08, UC10, UC20, FR07, FR08, FR12, FR16, FR25 | Xem bảng ở mục 1.3: chi tiết đơn, danh sách đơn, mua lại, đánh giá của tôi, thông báo, tài khoản của tôi, đổi mật khẩu, chặn đặt khi vượt tồn kho, lưu địa chỉ mặc định |
| **Thanh toán trực tuyến Sandbox** (mới) | UC07, FR11, FR22, FR23, NFR02, NFR15 | Cổng giả lập có nhãn SANDBOX, không nhận thông tin thẻ; một giao dịch cho cả nhóm đơn; mỗi nhóm chỉ một giao dịch đang hiệu lực (ràng buộc duy nhất trong DB); giữ kho 15 phút tính từ lúc đặt, thanh toán lại không kéo dài hạn; kết quả cổng được ký HMAC-SHA256, đối chiếu chữ ký + số tiền + mã giao dịch + mã nhóm đơn; mỗi giao dịch chỉ cập nhật đơn một lần (kết quả trùng bị bỏ qua); quá hạn tự hủy giao dịch + đơn + hoàn kho; kết quả thành công đến muộn (đơn đã hủy, hết hạn, hoặc nhóm đã thanh toán bằng giao dịch khác) ghi **Thanh toán muộn** và chuyển Chờ hoàn tiền; hủy đơn chưa thanh toán làm giao dịch đang chờ hết hiệu lực; hoàn tiền mô phỏng do Admin hoàn tất |
| **Module Người bán hoàn thiện, ảnh sản phẩm** (v5) | UC12-UC15, UC19, FR02, FR04, FR06, FR09, FR10; Open Issues UC13 #1, UC14 #1 | Xem bảng ở mục 1.2. Đóng hai Open Issue: giới hạn ảnh (số lượng, dung lượng, định dạng) và quy tắc sửa/xóa mã giảm giá đã có lượt dùng |
| **Quên mật khẩu bằng OTP** (v4) | FR01 mở rộng (Open Issue UC02) | OTP gửi email hoặc SMS tới đúng email/SĐT đăng ký; băm mã, hết hạn, giới hạn số lần sai và tần suất gửi; không lộ tài khoản có tồn tại; đặt lại xong gỡ khóa đăng nhập |
| **Hiển thị tất cả sản phẩm** (v4) | UC03 | Phân trang 24 sản phẩm/trang, mục Tất cả sản phẩm ở trang chủ, bộ lọc giữ nguyên khi chuyển trang |
| **Sao lưu / nạp dữ liệu PostgreSQL** (v4) | NFR13 | `check_db`, `export_data`, `import_data` (một giao dịch, đặt lại sequence) |
=======
| Thông báo trên website | FR25 | Đơn mới, đổi trạng thái, yêu cầu hủy, duyệt/khóa gian hàng |
| **Thanh toán trực tuyến Sandbox** (mới) | UC07, FR11, FR22, FR23, NFR02, NFR15 | Cổng giả lập có nhãn SANDBOX, không nhận thông tin thẻ; một giao dịch cho cả nhóm đơn; mỗi nhóm chỉ một giao dịch đang hiệu lực (ràng buộc duy nhất trong DB); giữ kho 15 phút tính từ lúc đặt, thanh toán lại không kéo dài hạn; kết quả cổng được ký HMAC-SHA256, đối chiếu chữ ký + số tiền + mã giao dịch + mã nhóm đơn; mỗi giao dịch chỉ cập nhật đơn một lần (kết quả trùng bị bỏ qua); quá hạn tự hủy giao dịch + đơn + hoàn kho; kết quả thành công đến muộn (đơn đã hủy, hết hạn, hoặc nhóm đã thanh toán bằng giao dịch khác) ghi **Thanh toán muộn** và chuyển Chờ hoàn tiền; hủy đơn chưa thanh toán làm giao dịch đang chờ hết hiệu lực; hoàn tiền mô phỏng do Admin hoàn tất |
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
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
<<<<<<< HEAD
- **Quên mật khẩu:** chưa gửi thử email/SMS thật (không có mạng); SMS chỉ có sẵn Twilio (chưa kiểm chứng với dịch vụ thật; Twilio thử nghiệm thường chỉ gửi tới số đã xác minh) và điểm nối cho nhà cung cấp Việt Nam, chưa tích hợp sẵn eSMS/SpeedSMS. Chưa có OTP khi đăng ký (xác minh email/SĐT) và chưa đổi mật khẩu khi đã đăng nhập.
- **Sao lưu:** `export_data` đọc cả dữ liệu vào bộ nhớ nên phù hợp dữ liệu cỡ đồ án; dữ liệu lớn dùng `pg_dump`. Không sao lưu ảnh trong `media/`.
- Chưa có giao diện admin xem danh sách `RefundRecord` riêng (xem được trong `/admin/` nếu đăng ký; hiện chỉ hiển thị trạng thái qua nút Hoàn tiền).
- Hết hạn giữ kho và các tác vụ theo hạn vẫn chạy "lười" khi mở trang đơn hàng / kênh quản lý, hoặc bằng `python manage.py process_timeouts --loop 60` (chưa dùng Celery/cron).
- **Ảnh sản phẩm:** chưa có ảnh nhỏ (thumbnail) riêng, mọi nơi dùng ảnh 1200 px được CSS thu nhỏ nên trang có nhiều sản phẩm tải hơi nặng; chưa có kéo thả sắp xếp thứ tự ảnh phụ; chưa có ảnh/logo cho gian hàng; chưa có ảnh biến thể (màu) riêng.
- **Người bán:** chưa có trả lời đánh giá của khách; chưa nhân bản sản phẩm, nhập/xuất sản phẩm hàng loạt bằng Excel/CSV; chưa xuất danh sách đơn ra file; chưa có lịch sử thay đổi giá/tồn kho (chỉ có nhật ký tồn khi đơn phát sinh); mã giảm giá chưa giới hạn theo sản phẩm hay theo từng khách.
- **Khách hàng (v6) - chưa làm:**
  - **Chưa xem giao diện bằng mắt.** Bố cục (thanh tiến trình, tab, thẻ đơn, giao diện điện thoại) viết theo các lớp CSS có sẵn và chỉ kiểm tra bằng test HTTP, đọc HTML và duyệt thử với dữ liệu mẫu. Nếu có chỗ lệch hoặc vỡ bố cục, chụp màn hình gửi lại để chỉnh `catalog/static/catalog/css/app.css` (phần "v6" ở cuối file).
  - **Chưa chạy trên PostgreSQL**: 161 test đạt trên SQLite. Truy vấn danh sách đơn dùng `distinct()` và `Prefetch` nên cần chạy `python manage.py test` trên PostgreSQL của bạn để chắc chắn.
  - Nút *Thanh toán* ở chi tiết đơn thanh toán **cả nhóm đơn** (đúng quy định thanh toán một lần cho nhóm), không thanh toán riêng từng đơn; chưa có đồng hồ đếm ngược hạn giữ kho (chỉ hiện giờ hết hạn).
  - Chưa cho **sửa / xóa đánh giá** và chưa có ảnh trong đánh giá (tài liệu quy định mỗi sản phẩm một đánh giá, sửa/xóa nằm ngoài phạm vi).
  - Chưa có: danh sách yêu thích, so sánh sản phẩm, nhiều địa chỉ nhận hàng (hiện chỉ một địa chỉ mặc định), chọn một phần sản phẩm trong giỏ để đặt, hủy cả nhóm đơn một lần, in/tải hóa đơn cho khách, theo dõi hành trình vận chuyển (chưa tích hợp API đơn vị vận chuyển), xóa thông báo, thông báo qua email/SMS, đổi email hoặc tên đăng nhập, xóa tài khoản, OTP khi đăng ký.
  - Tài khoản đăng ký bằng số điện thoại không đổi được số điện thoại (là tên đăng nhập).
  - Đặt hàng chưa kiểm tra định dạng số điện thoại người nhận (chỉ bắt buộc không rỗng); chưa sửa vì các test cũ đặt hàng với số rút gọn.
  - **Thanh toán (v6.1) chưa kiểm chứng với ZaloPay thật**: toàn bộ kiểm tra dùng phản hồi giả lập. Chưa xác nhận được trang giả lập ngân hàng Napas hiển thị "20 000 VND" là do trang đó hay do dữ liệu gửi đi (dữ liệu gửi đi đã kiểm tra là đúng, xem mục 1.4). Việc ZaloPay Sandbox treo ở trang kết quả nằm ngoài mã dự án; v6.1 chỉ giúp website tự phát hiện thanh toán xong. Khung chờ ở tab cũ (`pay.js`) chưa được thử trên trình duyệt thật; nếu trình duyệt chặn mở tab mới, hãy cho phép cửa sổ bật lên của trang web.
  - Khi chạy local không có `ZALOPAY_CALLBACK_URL` công khai, kết quả chỉ về nhờ hỏi lại ZaloPay (đối soát), có thể trễ vài giây so với khi có callback.
  - Thay đổi hành vi cần biết: trang Thông báo không còn tự đánh dấu đã đọc khi mở.
=======
- Chưa có giao diện admin xem danh sách `RefundRecord` riêng (xem được trong `/admin/` nếu đăng ký; hiện chỉ hiển thị trạng thái qua nút Hoàn tiền).
- Hết hạn giữ kho và các tác vụ theo hạn vẫn chạy "lười" khi mở trang đơn hàng / kênh quản lý, hoặc bằng `python manage.py process_timeouts --loop 60` (chưa dùng Celery/cron).
- Sản phẩm chưa có tải **hình ảnh** (tài liệu chưa quy định giới hạn ảnh, mục Open Issues UC13).
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
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
<<<<<<< HEAD
accounts/           hồ sơ và vai trò, đăng ký/đăng nhập, khóa đăng nhập, phiên hết hạn, quên mật khẩu OTP (otp.py, sms.py), tài khoản của tôi và đổi mật khẩu (v6)
catalog/            sản phẩm + ảnh (images.py), tìm kiếm có phân trang, gợi ý + lệnh check_db / export_data / import_data
shopping/           giỏ hàng, đặt hàng, mã giảm giá, hủy đơn, đánh giá, thống kê, kênh quản lý
                    customer_views.py (v6: danh sách và chi tiết đơn, mua lại, đánh giá của tôi, thông báo), tests_customer.py (39 test v6), tests_payment_wait.py (11 test v6.1)
                    payments.py (thanh toán: lõi chung, cổng giả lập, ZaloPay, hoàn tiền), zalopay.py (gọi API ZaloPay + ký MAC), moderation.py (duyệt/khóa/gỡ), product_views.py (Người bán quản lý sản phẩm, ảnh, kho nhanh), vendor_views.py (đánh giá, thông tin gian hàng, phiếu giao vận, vòng đời mã giảm giá),
=======
accounts/           hồ sơ và vai trò, đăng ký/đăng nhập, khóa đăng nhập, phiên hết hạn
catalog/            sản phẩm, tìm kiếm, gợi ý (bản trước) + cột mới cho gian hàng
shopping/           giỏ hàng, đặt hàng, mã giảm giá, hủy đơn, đánh giá, thống kê, kênh quản lý
                    payments.py (thanh toán: lõi chung, cổng giả lập, ZaloPay, hoàn tiền), zalopay.py (gọi API ZaloPay + ký MAC), moderation.py (duyệt/khóa/gỡ), product_views.py (Người bán quản lý sản phẩm),
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
                    admin_views.py (giao diện Quản trị viên), tests.py + tests_v2.py + tests_zalopay.py
chatbot/            hội thoại, che thông tin cá nhân, gọi LLM, API JSON
```
