from .base import *  # noqa
import dj_database_url


DATABASES = {
    "default": dj_database_url.config(
        default=env("DATABSE_URL"),  # type: ignore
        conn_max_age=600,
        conn_health_checks=True,
    )
}
