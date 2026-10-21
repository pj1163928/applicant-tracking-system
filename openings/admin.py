from django.contrib import admin

from accounts.permissions import eligible_authorities
from openings.models import JobOpening, OpeningEvent, Skill


class OpeningEventInline(admin.TabularInline):
    """An opening's event history, read-only: only the closure services write it."""

    model = OpeningEvent
    fields = ["kind", "by", "at", "note"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(JobOpening)
class JobOpeningAdmin(admin.ModelAdmin):
    list_display = ["title", "department", "status", "designated_authority", "updated_at"]
    list_filter = ["status", "department"]
    search_fields = ["title", "department", "location"]
    # Closing goes through the app's Close action, which writes the "closed" event.
    readonly_fields = ["status", "created_at", "updated_at"]
    inlines = [OpeningEventInline]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # The admin offers and accepts the same eligible staff as the app's form.
        if db_field.name == "designated_authority":
            kwargs["queryset"] = eligible_authorities()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]

    def has_delete_permission(self, request, obj=None) -> bool:
        # Skills are retired, never deleted, so openings that list them keep them.
        return False
