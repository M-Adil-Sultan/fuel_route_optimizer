from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('api/route/', views.calculate_route, name='calculate_route'),
]
