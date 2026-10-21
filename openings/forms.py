from django import forms
from django.contrib.auth.models import User

from accounts.permissions import eligible_authorities
from accounts.roles import role_label
from config.forms import DaisyUIFormMixin
from openings.models import JobOpening
from openings.services import SKILL_NAME_MAX_LENGTH


class AuthorityChoiceField(forms.ModelChoiceField):
    """Pick a designated authority, shown as "Name · Role"."""

    def label_from_instance(self, user: User) -> str:
        return f"{user.get_full_name() or user.username} · {role_label(user)}"


class JobOpeningForm(DaisyUIFormMixin, forms.ModelForm):
    """Edit an opening's details. The designated authority is not changed here.

    Nor is the status: closing goes through ``openings.services.close_opening()``,
    which writes the opening's "closed" event. New openings start open.
    """

    CLASSES = {
        "designated_authority": ("select w-full", "select-error"),
        "description": ("textarea w-full", "textarea-error"),
    }

    class Meta:
        model = JobOpening
        fields = ["title", "department", "location", "description"]
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
            "designated_authority",
            "description",
        ]


class SkillAttachForm(DaisyUIFormMixin, forms.Form):
    """Add a skill to an opening by name: an existing one, or a new one created inline.

    Only the typing is checked here; ``openings.services.attach_skill()``
    applies the rules (capitals ignored, retired skills refused).
    """

    name = forms.CharField(
        label="Add a skill",
        max_length=SKILL_NAME_MAX_LENGTH,
        error_messages={"required": "Type a skill name."},
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "list": "skill-suggestions",
                "placeholder": "For example Python",
            }
        ),
        help_text="Pick a suggestion, or type a new skill to create it.",
    )


class CloseOpeningForm(DaisyUIFormMixin, forms.Form):
    """Confirm closing an opening, with an optional note for its event history."""

    CLASSES = {"note": ("textarea w-full", "textarea-error")}

    note = forms.CharField(
        label="Note",
        required=False,
        max_length=500,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "For example: Budget moved to next year."}
        ),
        help_text="Shown in the opening's history, and in the email to the designated authority.",
    )
