from django.contrib import admin

from .models import (CancelRequest, CartItem, Coupon, CouponUse, Notification, Order, OrderGroup, OrderItem,
                     OrderStatusLog, PaymentTransaction, Review)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("variant", "product_name", "variant_name", "unit_price", "qty")
    can_delete = False


class StatusLogInline(admin.TabularInline):
    model = OrderStatusLog
    extra = 0
    readonly_fields = ("at", "old_status", "new_status", "actor", "note")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "shop", "status", "payment_status", "total", "created")
    list_filter = ("status", "payment_status", "shop")
    inlines = [OrderItemInline, StatusLogInline]
    readonly_fields = ("group", "shop", "shop_coupon", "subtotal", "shop_discount", "global_discount",
                       "shipping_fee", "total", "created")


@admin.register(OrderGroup)
class OrderGroupAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "recipient_name", "payment_method", "total", "created")
    search_fields = ("recipient_name", "user__username")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "scope", "shop", "kind", "value", "min_order", "used_count", "max_uses", "expires")
    list_filter = ("scope", "kind")
    search_fields = ("code",)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


admin.site.register(CouponUse)
admin.site.register(CancelRequest)
admin.site.register(CartItem)
admin.site.register(Review)
admin.site.register(Notification)


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ("ref", "group", "amount", "status", "refund_status", "created", "processed_at")
    list_filter = ("status", "refund_status")
    search_fields = ("ref",)
    readonly_fields = ("ref", "group", "amount", "gateway_status", "created", "processed_at")
