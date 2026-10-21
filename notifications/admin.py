from django.contrib import admin

from applications.admin import ViewOnlyAdmin
from notifications.models import CandidateMessage


@admin.register(CandidateMessage)
class CandidateMessageAdmin(ViewOnlyAdmin):
    """The email log is a record of what was sent, so it is read-only."""

    list_display = ["subject", "candidate", "kind", "sent_at"]
    list_filter = ["kind"]
    search_fields = ["candidate__first_name", "candidate__last_name", "candidate__email"]
