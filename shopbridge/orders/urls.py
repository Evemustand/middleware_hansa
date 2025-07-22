from django.urls import path
from .views import WooWebhookView

urlpatterns = [
    path('woo-webhook/', WooWebhookView.as_view(), name='woo-webhook'),
]
