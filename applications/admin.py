from django.contrib import admin

from applications.models import Application, StageChange


class ViewOnlyAdmin(admin.ModelAdmin):
    """Look, but never add, change or delete.

    Applications are created only by ``record_application()``, which writes the
    first history row with them, and stage history is permanent. Editing either
    here would get around those rules.
    """

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class StageChangeInline(admin.TabularInline):
    model = StageChange
    fields = ["from_stage", "to_stage", "changed_by", "changed_at", "cause", "note"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Application)
class ApplicationAdmin(ViewOnlyAdmin):
    list_display = ["candidate", "opening", "stage", "source", "created_at"]
    list_filter = ["stage", "source"]
    search_fields = ["candidate__first_name", "candidate__last_name", "opening__title"]
    inlines = [StageChangeInline]


@admin.register(StageChange)
class StageChangeAdmin(ViewOnlyAdmin):
    list_display = ["application", "from_stage", "to_stage", "changed_by", "changed_at", "cause"]
    list_filter = ["to_stage", "cause"]
