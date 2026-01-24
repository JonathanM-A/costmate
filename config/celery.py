import os
from celery import Celery
from celery.schedules import crontab
from celery.signals import celeryd_init

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")

app = Celery("costnav")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()


@celeryd_init.connect
def init_sentry(**kwargs):
    """Initialize Sentry for Celery workers."""
    from django.conf import settings

    if hasattr(settings, "SENTRY_DSN") and settings.SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.redis import RedisIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[
                CeleryIntegration(
                    monitor_beat_tasks=True,
                    propagate_traces=True,
                ),
                RedisIntegration(),
            ],
            environment=getattr(settings, "SENTRY_ENVIRONMENT", "production"),
            traces_sample_rate=getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.1),
        )