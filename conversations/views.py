from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from conversations.models import Conversation


@login_required
def conversation_list(request):
    conversations = (
        Conversation.objects.filter(tenant_id=request.user.tenant_id)
        .select_related("end_user")
        .order_by("-last_message_at", "-pk")
    )

    return render(
        request,
        "conversations/conversation_list.html",
        {"conversations": conversations},
    )


@login_required
def conversation_detail(request, pk):
    conversation = get_object_or_404(
        Conversation.objects.select_related("end_user"),
        pk=pk,
        tenant_id=request.user.tenant_id,
    )

    messages = conversation.message_set.all().order_by("created_at", "pk")

    return render(
        request,
        "conversations/conversation_detail.html",
        {
            "conversation": conversation,
            "messages": messages,
        },
    )
