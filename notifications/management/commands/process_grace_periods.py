"""The daily grace-period run: reminders, auto-cancellations and overdue flags.

Schedule it once a day (how is left to deployment). Running it more than once
on the same day is safe: it sends and writes nothing new.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from openings.services import process_grace_periods


class Command(BaseCommand):
    help = (
        "Send the grace-period reminders due today, cancel the remaining applications of "
        "auto-cancel grace periods that have ended, and flag ended flag-only ones as overdue."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--today",
            metavar="YYYY-MM-DD",
            help="Run as if it were this date (for demos and manual testing). "
            "Defaults to today in the project time zone.",
        )

    def handle(self, *args, **options) -> None:
        today = parse_today(options["today"])
        run = process_grace_periods(today=today)
        self.stdout.write(f"Grace periods for {today.isoformat()}")
        self.stdout.write(f"Reminders sent: {run.reminders_sent}")
        if run.expired:
            self.stdout.write(f"Grace periods ended: {', '.join(run.expired)}")
        else:
            self.stdout.write("Grace periods ended: none")
        for warning in run.warnings:
            self.stderr.write(self.style.WARNING(warning))
        self.stdout.write(self.style.SUCCESS("Done."))


def parse_today(value: str | None) -> date:
    """Return the ``--today`` date, or today in the project time zone if none was given."""
    if not value:
        return timezone.localdate()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise CommandError(f"--today must be a date like 2026-11-03, not {value!r}.") from None
