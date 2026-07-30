from django.urls import path

from . import views

urlpatterns = [
    path("datasets", views.DatasetListView.as_view(), name="dataset-list"),
    path("datasets/upload", views.DatasetUploadView.as_view(), name="dataset-upload"),
    path("datasets/<int:dataset_id>/history", views.DatasetHistoryView.as_view(), name="dataset-history"),
    path("chat", views.ChatView.as_view(), name="chat"),
]
