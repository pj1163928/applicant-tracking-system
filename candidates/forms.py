from django import forms

from candidates.models import Candidate


class CandidateForm(forms.ModelForm):
    """Add or edit a candidate's contact details."""

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

    # DaisyUI classes (normal, invalid), written out in full so Tailwind finds them.
    CLASSES = {"notes": ("textarea w-full", "textarea-error")}
    DEFAULT_CLASSES = ("input w-full", "input-error")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = self.CLASSES.get(name, self.DEFAULT_CLASSES)[0]

    def full_clean(self) -> None:
        """Validate, then mark each invalid input in red and for screen readers."""
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                attrs = self.fields[name].widget.attrs
                attrs["class"] += " " + self.CLASSES.get(name, self.DEFAULT_CLASSES)[1]
                attrs["aria-invalid"] = "true"
