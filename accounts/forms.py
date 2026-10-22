from django import forms
from django.contrib.auth.models import User

from accounts.permissions import eligible_authorities
from accounts.services import responsible_openings
from config.forms import DaisyUIFormMixin
from openings.forms import AuthorityChoiceField
from openings.models import JobOpening


class DeactivateStaffForm(DaisyUIFormMixin, forms.Form):
    """Pick a new designated authority for each opening a departing staff member is responsible for.

    One required field per opening, open or closed, named ``opening_<pk>``.
    The choices *and* the validation come from ``eligible_authorities()``,
    leaving out the person leaving. ``accounts.services.deactivate_staff()``
    checks the same rules again, so they hold whatever is posted.
    """

    DEFAULT_CLASSES = ("select w-full", "select-error")

    def __init__(self, *args, user: User, **kwargs) -> None:
        self.openings = list(responsible_openings(user).select_related("designated_authority"))
        super().__init__(*args, **kwargs)
        for opening in self.openings:
            self.fields[f"opening_{opening.pk}"] = AuthorityChoiceField(
                queryset=eligible_authorities().exclude(pk=user.pk),
                label=f"New authority for {opening.title}",
                error_messages={
                    "required": f"Pick who takes over {opening.title}.",
                    "invalid_choice": "Pick an active Admin, Recruiter or Hiring Manager.",
                },
            )
        # DaisyUIFormMixin styled the fields that existed when it ran; style these too.
        for field in self.fields.values():
            field.widget.attrs["class"] = self.DEFAULT_CLASSES[0]

    def rows(self) -> list[tuple[JobOpening, forms.BoundField]]:
        """Each opening with its picker, for the page to draw."""
        return [(opening, self[f"opening_{opening.pk}"]) for opening in self.openings]

    def reassignments(self) -> dict[JobOpening, User]:
        """The cleaned choices, as ``deactivate_staff()`` takes them."""
        return {opening: self.cleaned_data[f"opening_{opening.pk}"] for opening in self.openings}
