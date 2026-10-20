from django.contrib import admin

from candidates.models import Candidate, Source


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ["last_name", "first_name", "email", "phone", "created_at"]
    search_fields = ["first_name", "last_name", "email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name"]

    def has_delete_permission(self, request, obj=None) -> bool:
        # Sources are retired, never deleted, so old applications keep their source.
        return False
