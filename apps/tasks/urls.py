from django.urls import path

from . import views

urlpatterns = [
    path(
        '<str:task_id>/',
        views.async_task_status,
        name='async_task_status',
    ),
]
