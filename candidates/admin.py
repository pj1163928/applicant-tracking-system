from django.contrib import admin

from accounts.permissions import can_delete_candidates
from candidates.models import Candidate, Source


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ["last_name", "first_name", "email", "phone", "is_archived", "created_at"]
    list_filter = ["is_archived"]
    search_fields = ["first_name", "last_name", "email"]
    # Archiving goes through candidates.services, which refuses while an application is active.
    readonly_fields = ["is_archived", "archived_at", "created_at", "updated_at"]

    def has_delete_permission(self, request, obj=None) -> bool:
        # Permanent delete is for Admins only, whatever Django permissions say.
        return can_delete_candidates(request.user)


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name"]

    def has_delete_permission(self, request, obj=None) -> bool:
        # Sources are retired, never deleted, so old applications keep their source.
        return False
