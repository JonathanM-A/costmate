from celery import shared_task
from .models import Subscription
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def deactivate_expired_subscriptions(self, customer_id):
    """Deactivate subscriptions that have expired for a given customer."""
    retry_info = f" (Attempt {self.request.retries + 1} of {self.max_retries})"
    try:
        subscription = Subscription.objects.get(user__stripe_customer_id=customer_id)
        if subscription.is_active:
            subscription.is_active = False
            subscription.save()
            logger.info(f"Deactivated subscription for customer ID {customer_id}")
    except Subscription.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f"Error deactivating subscription for customer ID {customer_id}: {str(e)}{retry_info}")
        self.retry(exc=e)
