from django.urls import path

from conversations.views import conversation_detail, conversation_list

urlpatterns = [
    path(
        "",
        conversation_list,
        name="conversation-list",
    ),
    path(
        "<int:pk>/",
        conversation_detail,
        name="conversation-detail",
    ),
]
