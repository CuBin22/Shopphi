"""GHN HTTP + báo giá. Token chỉ ở backend, không tự retry thao tác ghi."""
import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

from .services import OrderError


class GHNError(OrderError):
    def __init__(self, message, uncertain=True):
        super().__init__(message)
        self.uncertain = uncertain


def error_message(body):
    # Chỉ hiển thị thông điệp tự định nghĩa, không phản chiếu dữ liệu/credentials từ upstream.
    code = body.get("code_message") if isinstance(body, dict) else None
    return {
        "SHOP_INFO_ERROR": "Kho GHN thiếu hoặc sai địa chỉ. Vui lòng cập nhật địa chỉ lấy hàng trên trang GHN.",
        "CLIENT_NOT_OWNER_OF_SHOP": "Shop ID GHN không thuộc tài khoản API đã cấu hình.",
        "ROUTE_NOT_FOUND_SERVICE": "GHN chưa hỗ trợ tuyến giao hàng này với dịch vụ đã chọn.",
    }.get(code, "GHN từ chối yêu cầu. Kiểm tra token, kho, địa chỉ và kiện hàng.")


def request(path, payload=None, shop_id=None, method="POST"):
    if not settings.GHN_TOKEN:
        raise GHNError("Chưa cấu hình GHN_TOKEN trên máy chủ.", uncertain=False)
    if settings.GHN_API_URL not in ("https://dev-online-gateway.ghn.vn", "https://online-gateway.ghn.vn"):
        raise GHNError("GHN_API_URL không hợp lệ.", uncertain=False)
    url = settings.GHN_API_URL + "/shiip/public-api/" + path
    headers = {"Token": settings.GHN_TOKEN, "Content-Type": "application/json"}
    if shop_id:
        headers["ShopId"] = str(shop_id)
    body = None
    if method == "GET":
        if payload:
            url += "?" + urllib.parse.urlencode(payload)
    else:
        body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=settings.GHN_TIMEOUT) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            failure = json.load(exc)
        except (ValueError, OSError):
            failure = {}
        raise GHNError(error_message(failure),
                       uncertain=exc.code >= 500 or exc.code in (408, 429)) from None
    except (urllib.error.URLError, OSError, ValueError):
        # Không đưa body/headers từ đối tác vào log hoặc màn hình (có thể chứa token/PII).
        raise GHNError("Không gọi được GHN. Kiểm tra token, kho, địa chỉ hoặc thử lại sau.") from None
    if not isinstance(result, dict) or result.get("code") != 200 or "data" not in result:
        code = result.get("code") if isinstance(result, dict) else None
        rejected = type(code) is int and 400 <= code < 500 and code not in (408, 429)
        raise GHNError(error_message(result), uncertain=not rejected)
    return result["data"]


def addresses(kind, parent=""):
    if kind not in ("province", "district", "ward"):
        raise GHNError("Loại địa chỉ không hợp lệ.")
    payload = {}
    if kind != "province":
        try:
            parent = int(parent)
            if parent <= 0:
                raise ValueError
        except (ValueError, TypeError):
            raise GHNError("Vui lòng chọn tỉnh/thành hoặc quận/huyện hợp lệ.") from None
        payload["province_id" if kind == "district" else "district_id"] = parent
    key = f"ghn:{settings.GHN_API_URL}:{kind}:{parent}"
    data = cache.get(key)
    if data is None:
        from catalog.models import Shop
        shop_id = settings.GHN_SHOP_ID or Shop.objects.filter(ghn_shop_id__gt=0).values_list("ghn_shop_id", flat=True).first()
        if not shop_id:
            raise GHNError("Chưa cấu hình kho GHN để tra địa chỉ.")
        data = request("master-data/" + kind, payload, shop_id=shop_id, method="GET") or []
        if not isinstance(data, list):
            raise GHNError("Danh mục địa chỉ GHN không hợp lệ.")
        cache.set(key, data, 3600)
    return data


def destination(info):
    try:
        province = next(p for p in addresses("province") if str(p["ProvinceID"]) == str(info.get("province_id")))
        district = next(d for d in addresses("district", province["ProvinceID"])
                        if str(d["DistrictID"]) == str(info.get("district_id")))
        ward = next(w for w in addresses("ward", district["DistrictID"])
                    if str(w["WardCode"]) == str(info.get("ward_code")))
    except (StopIteration, KeyError, TypeError):
        raise GHNError("Vui lòng chọn đủ tỉnh/thành, quận/huyện và phường/xã theo danh mục GHN.") from None
    return {"to_district_id": district["DistrictID"], "to_ward_code": str(ward["WardCode"]),
            "to_province_name": province["ProvinceName"], "to_district_name": district["DistrictName"],
            "to_ward_name": ward["WardName"], "is_new_to_address": False}


def package(lines):
    items = []
    for line in lines:
        v, qty = line["v"], line["qty"]
        dimensions = {k: getattr(v, k) for k in ("weight", "length", "width", "height")}
        if any(not isinstance(n, int) or n <= 0 for n in dimensions.values()):
            raise GHNError(f"Sản phẩm {v.product.name} chưa có đủ khối lượng/kích thước đóng gói.")
        items.append({"name": v.product.name, "code": str(v.pk), "quantity": qty,
                      "price": int(v.price), **dimensions})
    weight = sum(i["weight"] * i["quantity"] for i in items)
    # Ghép thành một kiện: xếp chồng theo chiều cao, giữ cạnh dài/rộng lớn nhất.
    size = {"length": max(i["length"] for i in items), "width": max(i["width"] for i in items),
            "height": sum(i["height"] * i["quantity"] for i in items)}
    if weight >= 20000 or any(n > 200 for n in size.values()):
        raise GHNError("Kiện hàng vượt giới hạn giao GHN hàng nhẹ (<20 kg, mỗi cạnh ≤200 cm). Vui lòng tách đơn.")
    return {"weight": weight, **size, "service_type_id": 2, "items": items}


def quote_checkout(checkout, info, method):
    dest = destination(info)
    for part in checkout.parts:
        if not part.shop.ghn_shop_id:
            raise GHNError(f"Gian hàng {part.shop.name} chưa được cấu hình kho GHN.")
        parcel = package(part.lines)
        value = part.subtotal - part.discount
        if value > 5000000:
            raise GHNError("Giá trị hàng vượt mức khai giá GHN 5.000.000đ; vui lòng tách đơn.")
        payload = {**dest, **parcel, "insurance_value": value}
        # COD bao gồm cước; lặp báo giá đến khi mức COD và cước nhất quán.
        fee = 0
        for _ in range(5):
            payload["cod_value"] = value + fee if method == "COD" else 0
            data = request("v2/shipping-order/fee", payload, shop_id=part.shop.ghn_shop_id)
            quoted = data.get("total") if isinstance(data, dict) else None
            if type(quoted) is not int or quoted < 0:
                raise GHNError("GHN trả về phí vận chuyển không hợp lệ.")
            if quoted == fee or method != "COD":
                fee = quoted
                break
            fee = quoted
        else:
            raise GHNError("Phí GHN đang thay đổi, vui lòng tính phí lại.")
        part.shipping = fee
        part.shipping_data = {**dest, **parcel, "insurance_value": value,
                              "shop_id": part.shop.ghn_shop_id, "api_url": settings.GHN_API_URL}
