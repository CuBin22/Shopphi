# Thiết kế: Tìm sản phẩm bằng Gemini Embeddings

## Mục tiêu

Giúp chatbot tìm đúng sản phẩm khi khách diễn đạt khác tên hoặc từ khóa trong dữ liệu. Gemini vẫn tạo câu trả lời dựa trên dữ liệu Shopphi hiện tại; embedding chỉ cải thiện bước truy xuất.

## Phương án đã chọn

Lưu embedding dưới dạng JSON trong PostgreSQL hiện có và tính cosine similarity trong ứng dụng. Đây là lựa chọn gọn cho quy mô đồ án, không cần cài extension `pgvector`. Không dùng Gemini File Search vì giá, tồn kho và thuộc tính sản phẩm cần đồng bộ trực tiếp với database Shopphi.

## Thiết kế

- Thêm bản ghi embedding gắn một-một với sản phẩm, gồm vector, model và fingerprint của nội dung đã nhúng.
- Nội dung tài liệu nhúng gồm tên, danh mục, thương hiệu, thẻ, tên biến thể, mô tả và thông số. Không nhúng giá/tồn kho; lấy các dữ liệu thay đổi này trực tiếp từ DB khi trả lời.
- Dùng Gemini `gemini-embedding-001`: `RETRIEVAL_DOCUMENT` cho sản phẩm, `RETRIEVAL_QUERY` cho câu hỏi. So sánh vector bằng cosine similarity.
- Xếp hạng kết quả theo cả độ tương đồng ngữ nghĩa và mức khớp từ khóa. Giữ giới hạn kết quả hiện tại để tránh câu trả lời liệt kê lan man.
- Khi thiếu key, lỗi API hoặc chưa có embedding, dùng truy xuất từ khóa hiện tại. Nội dung sản phẩm thay đổi thì fingerprint khiến embedding được tạo lại.
- Cấu hình model embedding riêng trong `.env`; API key vẫn chỉ nằm phía máy chủ.

## Ngoài phạm vi

Không thêm `pgvector`, không thay đổi giao diện chatbot, không nhúng đơn hàng hay địa chỉ khách hàng, không gửi giá/tồn kho thay đổi sang dịch vụ embedding.

## Kiểm tra

Kiểm tra migration và Django system check; xác minh cách xếp hạng hoạt động trên bộ dữ liệu local nếu Gemini key hợp lệ. Không ghi key hoặc dữ liệu cá nhân vào log.
