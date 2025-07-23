from django.urls import path
from .views import WooWebhookView,recent_orders

urlpatterns = [
    path('', WooWebhookView.as_view(), name='woo-webhook'),
    path('api/woo-webhook/', WooWebhookView.as_view(), name='woo_webhook'),
    path('api/woo-webhook/logs/', recent_orders, name='woo_recent_orders'),
]
