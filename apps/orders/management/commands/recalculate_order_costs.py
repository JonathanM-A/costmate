from django.core.management.base import BaseCommand
from django.db import transaction
from apps.orders.models import Order
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Recalculate costs for all orders or specific orders'

    def add_arguments(self, parser):
        parser.add_argument(
            '--order-id',
            type=str,
            help='Recalculate costs for a specific order by ID',
        )
        parser.add_argument(
            '--user-id',
            type=str,
            help='Recalculate costs for all orders belonging to a specific user',
        )
        parser.add_argument(
            '--status',
            type=str,
            choices=['pending', 'completed', 'cancelled'],
            help='Recalculate costs for orders with a specific status',
        )

    def handle(self, *args, **options):
        order_id = options.get('order_id')
        user_id = options.get('user_id')
        status = options.get('status')

        # Build queryset based on options
        queryset = Order.objects.all()

        if order_id:
            queryset = queryset.filter(id=order_id)
            if not queryset.exists():
                self.stdout.write(
                    self.style.ERROR(f'Order with ID {order_id} not found.')
                )
                return

        if user_id:
            queryset = queryset.filter(created_by_id=user_id)
            if not queryset.exists():
                self.stdout.write(
                    self.style.ERROR(f'No orders found for user ID {user_id}.')
                )
                return

        if status:
            queryset = queryset.filter(status=status)

        total_orders = queryset.count()

        if total_orders == 0:
            self.stdout.write(self.style.WARNING('No orders found to recalculate.'))
            return

        self.stdout.write(
            self.style.SUCCESS(f'Found {total_orders} order(s) to recalculate.')
        )

        success_count = 0
        error_count = 0

        for order in queryset.iterator():
            try:
                with transaction.atomic():
                    # Recalculate costs for each order product first
                    for order_product in order.order_products.all():
                        order_product.save()

                    # Then recalculate order costs
                    order.calculate_costs()
                    order.save()

                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Recalculated costs for order {order.order_no}'
                        )
                    )
            except Exception as e:
                error_count += 1
                logger.error(f'Error recalculating costs for order {order.order_no}: {str(e)}')
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Failed to recalculate costs for order {order.order_no}: {str(e)}'
                    )
                )

        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(
            self.style.SUCCESS(f'Successfully recalculated: {success_count} order(s)')
        )
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f'Failed to recalculate: {error_count} order(s)')
            )
        self.stdout.write('=' * 50)
