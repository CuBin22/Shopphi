from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0003_adminlog")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="image",
            field=models.ImageField(blank=True, upload_to="products/", verbose_name="Ảnh sản phẩm"),
        ),
    ]
