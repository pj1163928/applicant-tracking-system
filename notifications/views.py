from django.views.generic import TemplateView

from notifications.attention import closures_awaiting_decision, restores_awaiting_choice


class AttentionView(TemplateView):
    """The Needs attention panel: decisions waiting on the signed-in user. Any role may open it."""

    template_name = "notifications/attention.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        items = closures_awaiting_decision(user) + restores_awaiting_choice(user)
        return super().get_context_data(**kwargs) | {
            "yours": [item for item in items if item.assigned_to_you],
            "others": [item for item in items if not item.assigned_to_you],
        }
