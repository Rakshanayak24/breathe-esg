from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('batches', views.IngestionBatchViewSet, basename='batch')
router.register('emission-records', views.EmissionRecordViewSet, basename='emissionrecord')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/login/', views.login_view, name='login'),
    path('auth/logout/', views.logout_view, name='logout'),
    path('auth/me/', views.me_view, name='me'),
    path('dashboard/stats/', views.dashboard_stats, name='dashboard-stats'),
]
