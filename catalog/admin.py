from django.contrib import admin, messages

from .models import AdminLog, Category, Keyword, Product, Shop, Variant


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "status", "status_reason", "created")
    list_filter = ("status",)
    search_fields = ("name", "owner__username")
    actions = ["duyet"]

    def _notify(self, shop, text):
        from shopping.services import notify
        notify(shop.owner, text, "/quan-ly/")

    def save_model(self, request, obj, form, change):
        old = Shop.objects.filter(pk=obj.pk).values_list("status", flat=True).first() if change else None
        if obj.status in (Shop.ACTIVE, Shop.PENDING):
            obj.status_reason = ""
        super().save_model(request, obj, form, change)
        if old and old != obj.status:
            AdminLog.objects.create(actor=request.user, target_type=AdminLog.SHOP, target_id=obj.pk, target_label=obj.name,
                                    action=f"DOI_TRANG_THAI ({old}->{obj.status})", reason=obj.status_reason)
            self._notify(obj, f'Gian hàng "{obj.name}": ' + {
                Shop.ACTIVE: "đã được duyệt / mở khóa, bạn có thể đăng bán.",
                Shop.REJECTED: f"bị từ chối xét duyệt. Lý do: {obj.status_reason}",
                Shop.LOCKED: f"bị khóa. Lý do: {obj.status_reason}",
                Shop.PENDING: "chuyển sang chờ duyệt."}[obj.status])

    @admin.action(description="Duyệt: chuyển sang Hoạt động")
    def duyet(self, request, qs):
        for shop in qs.filter(status__in=[Shop.PENDING, Shop.LOCKED]):
            shop.status, shop.status_reason = Shop.ACTIVE, ""
            shop.save()
            self._notify(shop, f'Gian hàng "{shop.name}" đã được duyệt, bạn có thể đăng bán.')
        from .services import refresh_keyword_counts
        refresh_keyword_counts()
        self.message_user(request, "Đã duyệt. Muốn khóa hoặc từ chối, mở gian hàng và nhập lý do.", messages.SUCCESS)


class VariantInline(admin.TabularInline):
    model = Variant
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "category", "status")
    list_filter = ("status", "category", "shop")
    search_fields = ("name", "tags", "brand")
    inlines = [VariantInline]

    def save_model(self, request, obj, form, change):
        old = Product.objects.filter(pk=obj.pk).values_list("status", flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        if old and old != obj.status and Product.REMOVED in (old, obj.status):
            AdminLog.objects.create(actor=request.user, target_type=AdminLog.PRODUCT, target_id=obj.pk, target_label=obj.name,
                                    action="GO_SAN_PHAM" if obj.status == Product.REMOVED else "KHOI_PHUC_SAN_PHAM",
                                    reason=obj.removal_reason)

    fieldsets = (
        (None, {"fields": ("shop", "category", "name", "brand", "tags", "description", "specs")}),
        ("Hiển thị", {"fields": ("status", "removal_reason")}),
    )


@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    list_display = ("phrase", "frequency", "match_count", "visible", "hidden_reason")
    list_filter = ("visible",)
    search_fields = ("phrase",)
    readonly_fields = ("plain", "frequency", "match_count", "hidden_by")
    actions = ["hien_lai"]

    def save_model(self, request, obj, form, change):
        if obj.visible:
            obj.hidden_reason, obj.hidden_by = "", None
        else:
            obj.hidden_by = request.user
        super().save_model(request, obj, form, change)
        from .services import count_matches
        obj.match_count = count_matches(obj.plain)
        obj.save(update_fields=["match_count"])
        if change:
            AdminLog.objects.create(actor=request.user, target_type=AdminLog.KEYWORD, target_id=obj.pk, target_label=obj.phrase,
                                    action="HIEN_TU_KHOA" if obj.visible else "AN_TU_KHOA", reason=obj.hidden_reason)

    @admin.action(description="Hiện lại trong gợi ý")
    def hien_lai(self, request, qs):
        qs.update(visible=True, hidden_reason="", hidden_by=None)
        self.message_user(request, "Đã hiện lại các từ khóa đã chọn.", messages.SUCCESS)


@admin.register(AdminLog)
class AdminLogAdmin(admin.ModelAdmin):
    list_display = ("at", "target_type", "target_label", "action", "actor", "reason")
    list_filter = ("target_type",)
    readonly_fields = ("at", "actor", "target_type", "target_id", "target_label", "action", "reason")

    def has_add_permission(self, request):
        return False
