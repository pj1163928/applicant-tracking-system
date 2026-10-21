import pytest
from django.db import IntegrityError, transaction

from notifications.models import CandidateMessage
from notifications.services import send_candidate_message

pytestmark = pytest.mark.django_db

CANCELLED = CandidateMessage.Kind.CANCELLED


def test_a_candidate_message_is_never_sent_twice(
    application, django_capture_on_commit_callbacks, mailoutbox
):
    with django_capture_on_commit_callbacks(execute=True):
        first = send_candidate_message(application, CANCELLED, occasion="closure-1")
    with django_capture_on_commit_callbacks(execute=True):
        again = send_candidate_message(application, CANCELLED, occasion="closure-1")

    assert first is not None
    assert again is None
    assert list(CandidateMessage.objects.values_list("pk", flat=True)) == [first.pk]
    assert [(m.to, m.subject, m.body) for m in mailoutbox] == [
        (["ann@example.com"], first.subject, first.body)
    ]

    # A new occasion (a later closure) is a different message, so it is sent.
    with django_capture_on_commit_callbacks(execute=True):
        later = send_candidate_message(application, CANCELLED, occasion="closure-2")

    assert later is not None
    assert CandidateMessage.objects.count() == 2
    assert len(mailoutbox) == 2


def test_the_database_refuses_a_second_copy_of_the_same_message(application):
    def copy() -> CandidateMessage:
        return CandidateMessage(
            candidate=application.candidate,
            application=application,
            kind=CANCELLED,
            occasion="closure-1",
            subject="Subject",
            body="Body",
        )

    CandidateMessage.objects.bulk_create([copy()])

    with pytest.raises(IntegrityError), transaction.atomic():
        CandidateMessage.objects.bulk_create([copy()])  # skips save() and the service
    assert CandidateMessage.objects.count() == 1


def test_a_rolled_back_message_is_neither_logged_nor_sent(
    application, django_capture_on_commit_callbacks, mailoutbox
):
    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(RuntimeError),
        transaction.atomic(),
    ):
        send_candidate_message(application, CANCELLED, occasion="closure-1")
        raise RuntimeError("the change that caused the email failed")

    assert CandidateMessage.objects.count() == 0
    assert mailoutbox == []

    # So the retry sends it.
    with django_capture_on_commit_callbacks(execute=True):
        assert send_candidate_message(application, CANCELLED, occasion="closure-1") is not None
    assert len(mailoutbox) == 1


def test_the_cancellation_email_names_the_opening_and_says_the_team_will_be_in_touch(
    application, django_capture_on_commit_callbacks, mailoutbox
):
    with django_capture_on_commit_callbacks(execute=True):
        message = send_candidate_message(application, CANCELLED, occasion="closure-1")

    assert message.subject == "Your application for Backend Developer"
    assert message.body.startswith("Hello Ann,\n\n")
    words = " ".join(message.body.split())
    assert "The position has now closed" in words
    assert "our team will be in touch to complete the next step" in words
    assert message.candidate == application.candidate
