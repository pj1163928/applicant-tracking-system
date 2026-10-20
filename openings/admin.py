from django.contrib import admin

from accounts.permissions import eligible_authorities
from openings.models import JobOpening


@admin.register(JobOpening)
class JobOpeningAdmin(admin.ModelAdmin):
    list_display = ["title", "department", "status", "designated_authority", "updated_at"]
    list_filter = ["status", "department"]
    search_fields = ["title", "department", "location"]
    readonly_fields = ["created_at", "updated_at"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # The admin offers and accepts the same eligible staff as the app's form.
        if db_field.name == "designated_authority":
            kwargs["queryset"] = eligible_authorities()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
