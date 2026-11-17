-- Shopphi: kich thuoc DONG GOI UOC TINH de thu GHN Sandbox.
-- Don vi: weight = gram; length, width, height = centimet.
-- Chi dien o trong; khong sua gia, ton kho, va thong so da co.
-- Chay tren Neon SQL Editor, database shopphi_import.

WITH package(product_id, product_name, weight, length, width, height) AS (
    VALUES
        (106, 'Tai nghe Bluetooth Sóng A1',          350, 22, 19,  8),
        (107, 'Tai nghe gaming Sóng G7',             650, 26, 23, 12),
        (108, 'Tai nghe có dây Sóng E3',             180, 16, 12,  5),
        (109, 'Loa Bluetooth mini Sóng Pop',         500, 18, 12, 10),
        (110, 'Sạc dự phòng Cổng 10000mAh',          350, 18, 11,  5),
        (111, 'Củ sạc nhanh 33W Cổng',               180, 12,  9,  6),
        (112, 'Cáp sạc USB-C bện dù',                 150, 18, 14,  4),
        (113, 'Ốp lưng điện thoại trong suốt',        120, 20, 12,  4),
        (114, 'Chuột không dây Cổng M2',             250, 15, 11,  7),
        (115, 'Bàn phím cơ Sóng K87',                500, 20, 15,  5),
        (116, 'Nồi chiên không dầu 5L',             6500, 47, 38, 42),
        (117, 'Ấm đun siêu tốc 1.8L',               1700, 26, 22, 25),
        (118, 'Máy xay sinh tố mini',               1600, 26, 18, 18),
        (119, 'Bình giữ nhiệt 750ml',                600, 30, 12, 12),
        (120, 'Nồi cơm điện 1.2L',                  3700, 33, 31, 31),
        (121, 'Máy hút bụi cầm tay',                3000, 46, 20, 20),
        (122, 'Đèn bàn LED chống cận',              1200, 45, 18, 12),
        (123, 'Bộ dao nhà bếp 5 món',               1100, 40, 16,  8),
        (125, 'Xe điều khiển từ xa',                1200, 36, 26, 18),
        (126, 'Robot biến hình',                     600, 24, 18, 10),
        (127, 'Bộ ghép hình 1000 mảnh',             1100, 38, 28,  7),
        (128, 'Búp bê vải',                          400, 28, 18, 10),
        (129, 'Bộ đồ chơi nhà bếp mini',            1600, 38, 30, 15),
        (130, 'Bộ xếp hình robot 300 mảnh',          850, 32, 24,  8)
), changed AS (
    UPDATE catalog_variant AS v
    SET weight = COALESCE(v.weight, package.weight),
        length = COALESCE(v.length, package.length),
        width  = COALESCE(v.width,  package.width),
        height = COALESCE(v.height, package.height)
    FROM package, catalog_product AS p
    WHERE v.product_id = p.id
      AND p.id = package.product_id
      AND p.name = package.product_name
      AND (v.weight IS NULL OR v.length IS NULL OR v.width IS NULL OR v.height IS NULL)
    RETURNING v.id
)
SELECT COUNT(*) AS variants_updated FROM changed;

-- Sau khi chay, kiem tra: incomplete_variants phai bang 0.
SELECT COUNT(*) AS incomplete_variants
FROM catalog_variant
WHERE weight IS NULL OR length IS NULL OR width IS NULL OR height IS NULL;
