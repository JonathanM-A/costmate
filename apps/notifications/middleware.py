from django.utils.deprecation import MiddlewareMixin
from .utils import update_notification_cache


class NotificationHeaderMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if (request.user.is_authenticated and 
            request.path.startswith('/api/') and 
            response.status_code == 200):

            count = update_notification_cache(request.user.id)
            response['X-Unread-Notifications'] = str(count)
        return response