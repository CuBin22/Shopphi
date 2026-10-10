import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopping', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='ordergroup',
            name='hold_until',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Hạn giữ kho (thanh toán trực tuyến)'),
        ),
        migrations.CreateModel(
            name='PaymentTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ref', models.CharField(max_length=40, unique=True, verbose_name='Mã giao dịch nội bộ')),
                ('amount', models.DecimalField(decimal_places=0, max_digits=12, verbose_name='Số tiền')),
                ('status', models.CharField(choices=[('CHO_THANH_TOAN', 'Chờ thanh toán'), ('THANH_CONG', 'Thành công'), ('THAT_BAI', 'Thất bại / hủy tại cổng'), ('HET_HAN', 'Hết hạn giữ kho'), ('HET_HIEU_LUC', 'Hết hiệu lực'), ('THANH_TOAN_MUON', 'Thanh toán muộn')], db_index=True, default='CHO_THANH_TOAN', max_length=16, verbose_name='Trạng thái')),
                ('refund_status', models.CharField(blank=True, choices=[('', 'Không'), ('CHO_HOAN_TIEN', 'Chờ hoàn tiền'), ('DA_HOAN_TIEN', 'Đã hoàn tiền')], default='', max_length=14, verbose_name='Hoàn tiền (mô phỏng)')),
                ('gateway_status', models.CharField(blank=True, max_length=12, verbose_name='Kết quả cổng trả về')),
                ('created', models.DateTimeField(default=django.utils.timezone.now)),
                ('processed_at', models.DateTimeField(blank=True, null=True, verbose_name='Thời điểm xử lý kết quả')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='shopping.ordergroup')),
            ],
            options={
                'verbose_name': 'Giao dịch thanh toán',
                'verbose_name_plural': 'Giao dịch thanh toán',
                'ordering': ['-created', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='paymenttransaction',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'CHO_THANH_TOAN')), fields=('group',), name='uq_one_active_txn_per_group'),
        ),
    ]
