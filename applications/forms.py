from django import forms

from applications.models import Application
from applications.services import application_refusal
from candidates.models import Candidate, Source
from config.forms import DaisyUIFormMixin
from openings.models import JobOpening


class CandidateChoiceField(forms.ModelChoiceField):
    """Pick a candidate, shown as "Name · email"."""

    def label_from_instance(self, candidate: Candidate) -> str:
        return f"{candidate.full_name} · {candidate.email}"


class OpeningChoiceField(forms.ModelChoiceField):
    """Pick an opening, shown as "Title · Department"."""

    def label_from_instance(self, opening: JobOpening) -> str:
        return f"{opening.title} · {opening.department}"


class SourceChoiceField(forms.ModelChoiceField):
    """Pick a source, shown as "Name · Category", with "(retired)" on a retired one."""

    def label_from_instance(self, source: Source) -> str:
        label = f"{source.name} · {source.get_category_display()}"
        return label if source.is_active else f"{label} (retired)"


class ReferredByMixin:
    """Shared by both application forms: "referred by" applies only to Referral sources.

    Pass ``refresh_url`` to have each field in ``REFRESH_FIELDS`` ask the server
    (through HTMX, on change) for fresh source fields, so "referred by" appears
    or disappears as the source changes.
    """

    REFRESH_FIELDS: tuple[str, ...] = ("source",)

    def __init__(self, *args, refresh_url: str = "", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if refresh_url:
            for name in self.REFRESH_FIELDS:
                self.fields[name].widget.attrs.update(
                    {"hx-get": refresh_url, "hx-trigger": "change"}
                )

    @property
    def shows_referred_by(self) -> bool:
        """True when the chosen source (submitted, or initial) is a Referral."""
        value = self["source"].value()
        if isinstance(value, Source):
            return value.category == Source.Category.REFERRAL
        if not str(value or "").isdigit():
            return False
        return Source.objects.filter(pk=value, category=Source.Category.REFERRAL).exists()

    def clean_referred_by(self) -> str:
        if not self.shows_referred_by:
            return ""
        return self.cleaned_data.get("referred_by", "").strip()


SELECT = ("select w-full", "select-error")


class ApplicationForm(ReferredByMixin, DaisyUIFormMixin, forms.ModelForm):
    """Record a new application: a candidate, an open opening and an active source.

    Each dropdown's queryset both lists the choices and validates the
    submitted pk, so a hand-made POST naming a closed opening or a retired
    source fails validation.
    """

    CLASSES = {"candidate": SELECT, "opening": SELECT, "source": SELECT}
    # Changing the candidate also re-fills the source from their latest application.
    REFRESH_FIELDS = ("candidate", "source")

    candidate = CandidateChoiceField(
        queryset=Candidate.objects.all(),
        error_messages={"required": "Pick the candidate who applied."},
    )
    opening = OpeningChoiceField(
        queryset=JobOpening.objects.accepting_applications(),
        error_messages={
            "required": "Pick the opening they applied for.",
            "invalid_choice": "Pick an open opening. Closed openings don't take new applications.",
        },
    )
    source = SourceChoiceField(
        queryset=Source.objects.active(),
        help_text="Where the application came from.",
        error_messages={
            "required": "Pick where the application came from.",
            "invalid_choice": "Pick an active source. Retired sources can't be used "
            "for new applications.",
        },
    )

    class Meta:
        model = Application
        fields = ["candidate", "opening", "source", "referred_by"]
        widgets = {"referred_by": forms.TextInput(attrs={"autocomplete": "off"})}
        labels = {"referred_by": "Referred by"}
        help_texts = {"referred_by": "Who referred the candidate, for example a current employee."}

    def clean(self) -> dict:
        cleaned = super().clean()
        candidate, opening = cleaned.get("candidate"), cleaned.get("opening")
        if candidate and opening:
            refusal = application_refusal(candidate, opening)
            if refusal is not None:
                # An error on "opening" also skips the model's generic unique-constraint message.
                self.add_error("opening", refusal)
        return cleaned


class ApplicationSourceForm(ReferredByMixin, DaisyUIFormMixin, forms.ModelForm):
    """Correct an existing application's source and "referred by".

    The candidate, opening and stage can't change here. The source choices are
    the active sources plus this application's own source, so a retired source
    it already has still shows and stays valid, but no other retired source can
    be picked.
    """

    CLASSES = {"source": SELECT}

    source = SourceChoiceField(
        queryset=Source.objects.none(),
        help_text="Where the application came from.",
        error_messages={
            "required": "Pick where the application came from.",
            "invalid_choice": "Pick an active source, or keep this application's own source.",
        },
    )

    class Meta:
        model = Application
        fields = ["source", "referred_by"]
        widgets = ApplicationForm.Meta.widgets
        labels = ApplicationForm.Meta.labels
        help_texts = ApplicationForm.Meta.help_texts

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["source"].queryset = Source.objects.active_or_current(self.instance.source)
