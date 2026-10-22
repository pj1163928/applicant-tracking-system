from django import forms
from django.contrib.auth.models import User

from accounts.permissions import eligible_authorities
from accounts.roles import role_label
from applications.models import Application
from config.forms import DaisyUIFormMixin
from openings.models import JobOpening
from openings.services import (
    GRACE_DAYS_MAX,
    GRACE_DAYS_MIN,
    SKILL_NAME_MAX_LENGTH,
    RestoreChoice,
)


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


class ChangeAuthorityForm(DaisyUIFormMixin, forms.Form):
    """Pick an opening's new designated authority, with an optional note saying why.

    The choices *and* the validation come from ``eligible_authorities()``,
    leaving out the current authority. ``openings.services.change_authority()``
    checks the same rule again, so it holds whatever is posted.
    """

    CLASSES = {
        "authority": ("select w-full", "select-error"),
        "note": ("textarea w-full", "textarea-error"),
    }

    authority = AuthorityChoiceField(
        queryset=eligible_authorities(),
        label="New designated authority",
        help_text="Any active Admin, Recruiter or Hiring Manager. They'll be emailed.",
        error_messages={
            "required": "Pick the new designated authority.",
            "invalid_choice": "Pick an active Admin, Recruiter or Hiring Manager.",
        },
    )
    note = forms.CharField(
        label="Note",
        required=False,
        max_length=500,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "For example: Morgan now leads the design team."}
        ),
        help_text="Shown in the opening's history, and in the email to the new authority.",
    )

    def __init__(self, *args, opening: JobOpening, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["authority"].queryset = eligible_authorities().exclude(
            pk=opening.designated_authority_id
        )


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


class GracePeriodForm(DaisyUIFormMixin, forms.Form):
    """Give a closed opening's remaining applicants a grace period: how long, and what then.

    Only the typing is checked here; ``openings.services.set_grace_period()``
    applies the rules.
    """

    CLASSES = {"action": ("radio radio-primary radio-sm", "radio-error")}

    days = forms.IntegerField(
        label="Days",
        min_value=GRACE_DAYS_MIN,
        max_value=GRACE_DAYS_MAX,
        initial=7,
        error_messages={
            "required": "Say how many days the applicants get.",
            "min_value": f"A grace period is at least {GRACE_DAYS_MIN} day.",
            "max_value": f"A grace period is at most {GRACE_DAYS_MAX} days.",
        },
        widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
        help_text=f"{GRACE_DAYS_MIN} to {GRACE_DAYS_MAX}. It ends that many days from today.",
    )
    action = forms.ChoiceField(
        label="When it ends",
        choices=JobOpening.GraceExpiryAction.choices,
        widget=forms.RadioSelect,
        error_messages={"required": "Choose what happens when the grace period ends."},
    )


class ExtendGracePeriodForm(DaisyUIFormMixin, forms.Form):
    """Move a grace period's end date, with a note saying why.

    Only the typing is checked here; ``openings.services.extend_grace_period()``
    checks the date against the current end and today.
    """

    CLASSES = {"note": ("textarea w-full", "textarea-error")}

    ends = forms.DateField(
        label="New end date",
        error_messages={
            "required": "Pick the new end date.",
            "invalid": "Pick the new end date.",
        },
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    note = forms.CharField(
        label="Why it's being extended",
        max_length=500,
        error_messages={"required": "Say why the grace period is being extended."},
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "For example: Final interviews moved to next week."}
        ),
        help_text="Shown in the opening's history.",
    )


class ReopenOpeningForm(DaisyUIFormMixin, forms.Form):
    """Confirm reopening an opening, with an optional note for its event history."""

    CLASSES = {"note": ("textarea w-full", "textarea-error")}

    note = forms.CharField(
        label="Note",
        required=False,
        max_length=500,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "For example: Budget approved after all."}
        ),
        help_text="Shown in the opening's history.",
    )


RESTORE, RESTORE_NONE = "restore", "none"


class RestoreApplicationsForm(DaisyUIFormMixin, forms.Form):
    """Tick which applicants cancelled at the latest closure go back where they were.

    The choices *and* the validation come from the selectable
    ``openings.services.restore_choices()``, so a hand-made POST naming an
    archived candidate, or anyone the closure didn't cancel, fails validation.
    ``restore_applications()`` checks the same rules again. The page draws the
    checklist itself, disabled rows included, and its two buttons send ``decision``.
    """

    applications = forms.ModelMultipleChoiceField(
        queryset=Application.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        error_messages={
            "invalid_choice": "Only applicants listed here who can be restored can be ticked.",
            "invalid_pk_value": "Only applicants listed here who can be restored can be ticked.",
        },
    )
    decision = forms.ChoiceField(
        choices=[(RESTORE, "Restore"), (RESTORE_NONE, "Don't restore anyone")],
        error_messages={"required": "Choose whether to restore anyone."},
    )

    def __init__(self, *args, choices: list[RestoreChoice], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        selectable = [choice.application.pk for choice in choices if choice.selectable]
        self.fields["applications"].queryset = Application.objects.filter(pk__in=selectable)

    def clean(self) -> dict:
        cleaned = super().clean()
        if cleaned.get("decision") == RESTORE_NONE:
            cleaned["applications"] = []
        elif "applications" in cleaned and not cleaned["applications"]:
            self.add_error(
                "applications", "Tick at least one applicant, or choose Don't restore anyone."
            )
        return cleaned
