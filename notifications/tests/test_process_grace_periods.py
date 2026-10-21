"""The daily ``process_grace_periods`` command."""

from datetime import date
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from applications.models import Application
from applications.stages import Stage
from openings.models import JobOpening, OpeningEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def in_grace(application, hiring_manager):
    """Ann's opening, closed, in an auto-cancel grace period set Nov 3 that ends Nov 10."""
    opening = application.opening
    JobOpening.objects.filter(pk=opening.pk).update(
        status=JobOpening.Status.CLOSED,
        grace_period_ends=date(2026, 11, 10),
        grace_expiry_action=JobOpening.GraceExpiryAction.AUTO_CANCEL,
        grace_period_set_on=date(2026, 11, 3),
    )
    OpeningEvent.objects.create(opening=opening, kind=OpeningEvent.Kind.CLOSED, by=hiring_manager)
    OpeningEvent.objects.create(
        opening=opening, kind=OpeningEvent.Kind.GRACE_PERIOD_SET, by=hiring_manager
    )
    return opening


def run(*args) -> tuple[str, str]:
    out, err = StringIO(), StringIO()
    call_command("process_grace_periods", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_today_option_sends_the_reminder_due_that_day_and_reports_it(
    in_grace, django_capture_on_commit_callbacks, mailoutbox
):
    with django_capture_on_commit_callbacks(execute=True):
        out, _ = run("--today", "2026-11-07")

    assert "Grace periods for 2026-11-07" in out
    assert "Reminders sent: 1" in out
    assert "Grace periods ended: none" in out
    assert [m.subject for m in mailoutbox] == [
        "3 days left on your application for Backend Developer"
    ]


def test_on_the_end_date_it_cancels_and_reports_the_opening_and_a_rerun_does_nothing(
    in_grace, application, django_capture_on_commit_callbacks, mailoutbox
):
    with django_capture_on_commit_callbacks(execute=True):
        out, _ = run("--today", "2026-11-10")
        again, _ = run("--today", "2026-11-10")

    assert "Grace periods ended: Backend Developer" in out
    assert "Grace periods ended: none" in again
    assert Application.objects.get(pk=application.pk).stage == Stage.REJECTED
    assert len(mailoutbox) == 1  # one cancellation email, never repeated


def test_a_skipped_opening_is_reported_as_a_warning(in_grace, hiring_manager):
    hiring_manager.is_active = False
    hiring_manager.save()

    _, err = run("--today", "2026-11-10")

    assert "Skipped Backend Developer" in err


def test_without_today_it_uses_the_project_date(in_grace, monkeypatch):
    monkeypatch.setattr("django.utils.timezone.localdate", lambda: date(2026, 11, 4))

    out, _ = run()

    assert "Grace periods for 2026-11-04" in out


def test_a_bad_today_is_refused(in_grace):
    with pytest.raises(CommandError, match="--today must be a date like 2026-11-03"):
        run("--today", "next tuesday")
