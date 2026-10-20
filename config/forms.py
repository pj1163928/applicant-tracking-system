"""Form helpers shared by every app."""


class DaisyUIFormMixin:
    """Give each widget its DaisyUI class, and mark invalid inputs for styling and screen readers.

    ``CLASSES`` maps a field name to its (normal, invalid) classes; other fields
    use ``DEFAULT_CLASSES``. Write class names out in full so Tailwind finds them.
    """

    CLASSES: dict[str, tuple[str, str]] = {}
    DEFAULT_CLASSES: tuple[str, str] = ("input w-full", "input-error")

    def __init__(self, *args, **kwargs) -> None:
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
