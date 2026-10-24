from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("shopping", "0004_vendor_images_coupon_active")]

    operations = [
        migrations.AlterField(
            model_name="paymenttransaction",
            name="provider",
            field=models.CharField(
                choices=[("SANDBOX", "Cổng giả lập"), ("ZALOPAY", "ZaloPay"), ("VNPAY", "VNPay")],
                default="SANDBOX", max_length=10, verbose_name="Cổng thanh toán"),
        ),
    ]
