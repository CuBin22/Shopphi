"""GHN HTTP + báo giá. Token chỉ ở backend, không tự retry thao tác ghi."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

from catalog.text import khong_dau

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
        shop_id = address_shop_id()
        data = request("master-data/" + kind, payload, shop_id=shop_id, method="GET") or []
        if not isinstance(data, list):
            raise GHNError("Danh mục địa chỉ GHN không hợp lệ.")
        cache.set(key, data, 3600)
    return data


def address_shop_id():
    from catalog.models import Shop
    shop_id = settings.GHN_SHOP_ID or Shop.objects.filter(ghn_shop_id__gt=0).values_list("ghn_shop_id", flat=True).first()
    if not shop_id:
        raise GHNError("Chưa cấu hình kho GHN để tra địa chỉ.")
    return shop_id


def new_addresses(kind, parent=""):
    if kind not in ("province", "ward"):
        raise GHNError("Loại địa chỉ GHN không hợp lệ.")
    payload = {"offset": 0, "limit": 200}
    path = "v3/master-data/province/all"
    if kind == "ward":
        try:
            parent = int(parent)
            if parent <= 0:
                raise ValueError
        except (ValueError, TypeError):
            raise GHNError("Không xác định được tỉnh/thành trong địa chỉ.") from None
        path = "v3/master-data/ward/all-by-province-id"
        payload["province_id"] = parent
    key = f"ghn:{settings.GHN_API_URL}:new:{kind}:{parent}"
    data = cache.get(key)
    if data is None:
        data = request(path, payload, shop_id=address_shop_id(), method="GET") or []
        if not isinstance(data, list):
            raise GHNError("Danh mục địa chỉ GHN không hợp lệ.")
        cache.set(key, data, 3600)
    return data


def _address_key(value):
    value = khong_dau(value).lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", value).strip() + " "


def _match_address_unit(text, rows, label, before=None):
    matches = []
    for row in rows:
        aliases = [row.get("name", ""), *(row.get("extension_names") or [])]
        for alias in aliases:
            key = _address_key(alias)
            if len(key.strip()) < 3:
                continue
            start = text.find(key)
            while start >= 0:
                matches.append((start + len(key), len(key), start, row))
                start = text.find(key, start + 1)
    if not matches:
        raise GHNError(f"Không nhận diện được {label} từ địa chỉ. Hãy ghi rõ tên phường/xã và tỉnh/thành.")
    if before is not None:
        earlier = [match for match in matches if match[0] <= before]
        if earlier:
            matches = earlier
    latest = max(end for end, _, _, _ in matches)
    matches = [match for match in matches if match[0] == latest]
    longest = max(length for _, length, _, _ in matches)
    best = {str(row.get("_id")): (row, start)
            for end, length, start, row in matches if length == longest}
    if len(best) != 1:
        raise GHNError(f"Địa chỉ khớp nhiều {label}. Hãy bổ sung tên phường/xã hoặc tỉnh/thành đầy đủ.")
    return next(iter(best.values()))


def _new_destination(address):
    text = _address_key(address)
    province, province_start = _match_address_unit(text, new_addresses("province"), "tỉnh/thành")
    ward, _ = _match_address_unit(text, new_addresses("ward", province["_id"]), "phường/xã", before=province_start)
    return {"to_ward_name": ward["name"], "to_province_name": province["name"], "is_new_to_address": True}


def _legacy_destination(info):
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


def destination(info):
    if isinstance(info, dict) and any(info.get(key) for key in ("province_id", "district_id", "ward_code")):
        return _legacy_destination(info)
    return _new_destination(info.get("address", "") if isinstance(info, dict) else info)


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
    legacy_address = not dest.get("is_new_to_address")
    for part in checkout.parts:
        if not part.shop.ghn_shop_id:
            raise GHNError(f"Gian hàng {part.shop.name} chưa được cấu hình kho GHN.")
        parcel = package(part.lines)
        value = part.subtotal - part.discount
        if value > 5000000:
            raise GHNError("Giá trị hàng vượt mức khai giá GHN 5.000.000đ; vui lòng tách đơn.")
        payload = {**dest, **parcel, "insurance_value": value}
        if not legacy_address:
            payload.update(to_name=info["name"], to_phone=info["phone"], to_address=info["address"],
                           payment_type_id=1, required_note="CHOXEMHANGKHONGTHU")
        # COD bao gồm cước; lặp báo giá đến khi mức COD và cước nhất quán.
        fee = 0
        for _ in range(5):
            if legacy_address:
                payload["cod_value"] = value + fee if method == "COD" else 0
            else:
                payload["cod_amount"] = value + fee if method == "COD" else 0
            endpoint = "v2/shipping-order/fee" if legacy_address else "v2/shipping-order/preview"
            data = request(endpoint, payload, shop_id=part.shop.ghn_shop_id)
            quoted = data.get("total", data.get("total_fee")) if isinstance(data, dict) else None
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
