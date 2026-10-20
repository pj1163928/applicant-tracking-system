from django import forms

from candidates.models import Candidate, Source
from config.forms import DaisyUIFormMixin


class CandidateForm(DaisyUIFormMixin, forms.ModelForm):
    """Add or edit a candidate's contact details."""

    CLASSES = {"notes": ("textarea w-full", "textarea-error")}

    class Meta:
        model = Candidate
        fields = ["first_name", "last_name", "email", "phone", "notes"]
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "off"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "off"}),
            "email": forms.EmailInput(attrs={"autocomplete": "off"}),
            "phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "off"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "email": "Stored in lowercase. Each email can belong to only one candidate.",
            "notes": "Anything useful about this candidate.",
        }


SOURCE_NAME_HELP = "Must be unique, ignoring capital letters."


class SourceForm(DaisyUIFormMixin, forms.ModelForm):
    """Add a source: a name and one of the four categories."""

    CLASSES = {"category": ("select w-full", "select-error")}

    class Meta:
        model = Source
        fields = ["name", "category"]
        widgets = {"name": forms.TextInput(attrs={"autocomplete": "off"})}
        help_texts = {
            "name": SOURCE_NAME_HELP,
            "category": "Used to group sources when comparing channels.",
        }


class SourceRenameForm(DaisyUIFormMixin, forms.ModelForm):
    """Rename a source to fix a typo. The category stays as it was created."""

    class Meta:
        model = Source
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"autocomplete": "off"})}
        help_texts = {"name": SOURCE_NAME_HELP}
