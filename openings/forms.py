from django import forms
from django.contrib.auth.models import User

from accounts.permissions import eligible_authorities
from accounts.roles import role_label
from config.forms import DaisyUIFormMixin
from openings.models import JobOpening


class AuthorityChoiceField(forms.ModelChoiceField):
    """Pick a designated authority, shown as "Name · Role"."""

    def label_from_instance(self, user: User) -> str:
        return f"{user.get_full_name() or user.username} · {role_label(user)}"


class JobOpeningForm(DaisyUIFormMixin, forms.ModelForm):
    """Edit an opening's details. The designated authority is not changed here."""

    CLASSES = {
        "status": ("select w-full", "select-error"),
        "designated_authority": ("select w-full", "select-error"),
        "description": ("textarea w-full", "textarea-error"),
    }

    class Meta:
        model = JobOpening
        fields = ["title", "department", "location", "status", "description"]
        widgets = {
            "title": forms.TextInput(attrs={"autocomplete": "off"}),
            "department": forms.TextInput(attrs={"autocomplete": "off"}),
            "location": forms.TextInput(attrs={"autocomplete": "off"}),
            "description": forms.Textarea(attrs={"rows": 6}),
        }
        help_texts = {
            "location": "For example a city, or Remote.",
            "description": "What the role involves and who you're looking for.",
        }


class JobOpeningCreateForm(JobOpeningForm):
    """Create an opening, including its required designated authority.

    The choices *and* the validation come from ``eligible_authorities()``, so a
    hand-made POST naming an Interviewer, a user without a role or an inactive
    user fails validation.
    """

    designated_authority = AuthorityChoiceField(
        queryset=eligible_authorities(),
        label="Designated authority",
        help_text="Makes this opening's offer and closure decisions. "
        "Any active Admin, Recruiter or Hiring Manager.",
        error_messages={
            "required": "Every opening needs a designated authority.",
            "invalid_choice": "Pick an active Admin, Recruiter or Hiring Manager.",
        },
    )

    class Meta(JobOpeningForm.Meta):
        fields = [
            "title",
            "department",
            "location",
            "status",
            "designated_authority",
            "description",
        ]
