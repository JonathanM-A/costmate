from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserPreferences
from .tasks import create_user_preferences

User = get_user_model()

@receiver(post_save, sender=User)
def create_related_models(sender, instance, created, **kwargs):
    if created and not instance.is_superuser:
        create_user_preferences.delay(instance.id) #type: ignore
        # create_user_subscription.delay(instance.id)  # type: ignore
        
