from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User


class StaffUserAdmin(UserAdmin):
    """Django's user admin, with ``is_active`` read-only on existing users.

    Deactivating someone goes through the app's staff page
    (``accounts.services.deactivate_staff()``), which first hands each of their
    openings to a new designated authority. New users still start active.
    """

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly.append("is_active")
        return readonly


admin.site.unregister(User)
admin.site.register(User, StaffUserAdmin)
