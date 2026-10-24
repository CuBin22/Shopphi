import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0002_shop_contact_shop_owner_shop_pickup_address_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Thời điểm')),
                ('target_type', models.CharField(choices=[('GIAN_HANG', 'Gian hàng'), ('SAN_PHAM', 'Sản phẩm'), ('TU_KHOA', 'Từ khóa')], max_length=10, verbose_name='Loại đối tượng')),
                ('target_id', models.PositiveIntegerField(verbose_name='Mã đối tượng')),
                ('target_label', models.CharField(blank=True, max_length=200, verbose_name='Đối tượng')),
                ('action', models.CharField(max_length=40, verbose_name='Thao tác')),
                ('reason', models.CharField(blank=True, max_length=255, verbose_name='Lý do')),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Người thực hiện')),
            ],
            options={
                'verbose_name': 'Nhật ký quản trị',
                'verbose_name_plural': 'Nhật ký quản trị',
                'ordering': ['-at', '-id'],
            },
        ),
    ]
