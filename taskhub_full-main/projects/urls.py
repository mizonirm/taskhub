from django.urls import path

from . import views

urlpatterns = [
    path("request/", views.request_project, name="request_project"),
    path("request/<int:pk>/<str:decision>/", views.review_request, name="review_request"),
    path("", views.project_list, name="project_list"),
    path("<int:pk>/", views.project_detail, name="project_detail"),
    path("<int:pk>/edit/", views.project_edit, name="project_edit"),
    path("<int:pk>/delete/", views.project_delete, name="project_delete"),
    path("<int:pk>/status/", views.project_status, name="project_status"),
    path("<int:pk>/members/add/", views.member_add, name="member_add"),
    path("<int:pk>/members/<int:user_id>/remove/", views.member_remove, name="member_remove"),
    path("<int:project_pk>/tasks/new/", views.task_create, name="task_create"),
    path("<int:project_pk>/tasks/<int:parent_pk>/subtasks/new/", views.task_create, name="subtask_create"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/<int:pk>/edit/", views.task_edit, name="task_edit"),
    path("tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),
    path("tasks/<int:pk>/status/", views.task_status, name="task_status"),
    path("<int:project_pk>/comments/add/", views.comment_add, name="comment_add"),
    path("<int:project_pk>/tasks/<int:task_pk>/comments/add/", views.comment_add, name="task_comment_add"),
    path("comments/<int:pk>/delete/", views.comment_delete, name="comment_delete"),
    path("<int:project_pk>/documents/upload/", views.document_upload, name="document_upload"),
    path("documents/<int:pk>/download/", views.document_download, name="document_download"),
    path("documents/<int:pk>/delete/", views.document_delete, name="document_delete"),
    path("notifications/", views.notifications_list, name="notifications"),
    path("notifications/read-all/", views.notifications_mark_all, name="notifications_read_all"),
    path("notifications/<int:pk>/open/", views.notification_open, name="notification_open"),
]
