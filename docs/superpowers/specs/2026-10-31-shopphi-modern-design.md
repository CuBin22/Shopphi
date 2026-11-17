# Shopphi Modern — giao diện thống nhất

## Ý định
Làm giao diện mua sắm, người bán và quản trị trông như cùng một sản phẩm; giúp người mua tìm và đặt hàng thuận tiện, giúp người bán/quản trị đọc dữ liệu và thao tác rõ ràng.

## Mục tiêu
- Giữ đỏ cam Shopphi làm màu nhận diện, phối với nền trắng/ngà nhạt, mực than và màu trạng thái có ý nghĩa.
- Chuẩn hóa typography, lưới khoảng cách, bo góc, viền, bóng, nút, trường nhập, bảng, thẻ và trạng thái tương tác.
- Áp dụng nhất quán cho storefront, chi tiết shop/sản phẩm, giỏ/checkout/đơn hàng, kênh người bán và quản trị.
- Bảo đảm bố cục đáp ứng trên desktop/mobile, focus bàn phím rõ và hỗ trợ giảm chuyển động.

## Ngoài phạm vi
- Không thay đổi nghiệp vụ, luồng thanh toán/giao hàng, quyền truy cập, dữ liệu sản phẩm hoặc nội dung.
- Không thay framework hoặc cài thư viện giao diện mới nếu CSS/template hiện tại đáp ứng được.

## Hướng đã chọn
- **Shopphi hiện đại** được chọn thay cho marketplace mô phỏng Shopee hoặc dashboard quản trị làm chủ đạo.
- Dấu ấn: đỏ cam dùng tiết chế cho hành động và điểm nhấn; nền trung tính và kiểu chữ rõ tạo cảm giác gọn, đáng tin.

## Ràng buộc và quyết định triển khai
- Dự án Django template, dùng hai stylesheet nền tảng/storefront và nhiều màn hình người bán/quản trị.
- Dùng CSS tokens làm nguồn màu, typography, spacing, radius, shadow; gom override trùng và giữ selector theo component.
- Chia triển khai theo vùng dùng chung: nền/header/footer, thành phần storefront, biểu mẫu/checkout, quản lý/bảng; giữ template/nghiệp vụ trừ khi cần chỉnh class để tái sử dụng.
- Ưu tiên thay đổi nhỏ, kiểm tra mỗi nhóm màn hình trước khi mở rộng.

## Chưa bao gồm
- Không thêm tính năng hay đổi hành vi để phục vụ việc làm đẹp.
- Không cam kết thay ảnh/nhãn hiệu sản phẩm hoặc tạo nội dung marketing mới.
