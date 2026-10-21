import pytest
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from applications.models import Application, StageChange
from applications.stages import Stage
from candidates.models import Candidate

pytestmark = pytest.mark.django_db

CREATE_URL = reverse("applications:create")


def counts() -> tuple[int, int]:
    return Application.objects.count(), StageChange.objects.count()


def message_texts(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


@pytest.mark.parametrize(
    ("user_fixture", "allowed"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", False),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_only_recruiters_and_admins_can_record_or_edit_applications(
    client, request, user_fixture, allowed, apply, ann, ben, backend, indeed, linkedin
):
    existing = apply(ben, backend, indeed)
    client.force_login(request.getfixturevalue(user_fixture))
    edit_url = reverse("applications:update", args=[existing.pk])

    statuses = [
        client.get(f"{CREATE_URL}?candidate={ann.pk}").status_code,
        client.post(
            CREATE_URL, {"candidate": ann.pk, "opening": backend.pk, "source": indeed.pk}
        ).status_code,
        client.get(edit_url).status_code,
        client.post(edit_url, {"source": linkedin.pk}).status_code,
    ]

    existing.refresh_from_db()
    if allowed:
        assert statuses == [200, 302, 200, 302]
        assert counts() == (2, 2)
        assert existing.source == linkedin
    else:
        assert statuses == [403, 403, 403, 403]
        assert counts() == (1, 1)
        assert existing.source == indeed


def test_anonymous_users_are_sent_to_log_in(client):
    response = client.get(CREATE_URL)

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


def test_recording_from_a_candidates_page_saves_at_applied_and_returns_there(
    client, recruiter, ann, backend, referral
):
    client.force_login(recruiter)

    response = client.post(
        f"{CREATE_URL}?candidate={ann.pk}",
        {
            "candidate": ann.pk,
            "opening": backend.pk,
            "source": referral.pk,
            "referred_by": "Dana Lee",
        },
    )

    assert response.status_code == 302
    assert response.url == ann.get_absolute_url()
    application = Application.objects.get()
    assert (application.stage, application.referred_by) == (Stage.APPLIED, "Dana Lee")
    first = application.stage_changes.get()
    assert (first.from_stage, first.to_stage, first.changed_by) == ("", Stage.APPLIED, recruiter)
    assert message_texts(response) == [
        "Recorded Ann Lee's application for Backend Developer, at Applied."
    ]


def test_recording_from_an_openings_page_returns_to_the_opening(
    client, recruiter, ann, backend, indeed
):
    client.force_login(recruiter)

    response = client.post(
        f"{CREATE_URL}?opening={backend.pk}",
        {"candidate": ann.pk, "opening": backend.pk, "source": indeed.pk},
    )

    assert response.url == backend.get_absolute_url()


def test_starting_from_an_opening_selects_it(client, recruiter, backend, qa, indeed):
    client.force_login(recruiter)

    response = client.get(f"{CREATE_URL}?opening={qa.pk}")

    assert response.context["form"]["opening"].value() == qa.pk
    assert response.context["back_url"] == qa.get_absolute_url()


def test_the_form_prefills_the_source_from_the_candidates_latest_application(
    client, recruiter, apply, ann, backend, qa, linkedin
):
    apply(ann, backend, linkedin)
    client.force_login(recruiter)

    response = client.get(f"{CREATE_URL}?candidate={ann.pk}")

    assert response.context["form"]["source"].value() == linkedin.pk
    assert f'<option value="{linkedin.pk}" selected>' in response.content.decode()


def test_a_candidate_with_no_earlier_application_gets_no_prefill(
    client, recruiter, ann, backend, indeed
):
    client.force_login(recruiter)

    response = client.get(f"{CREATE_URL}?candidate={ann.pk}")

    assert response.context["form"]["source"].value() is None


def test_the_create_page_refuses_to_start_from_a_closed_opening(client, recruiter, closed_opening):
    client.force_login(recruiter)

    response = client.get(f"{CREATE_URL}?opening={closed_opening.pk}")

    assert response.status_code == 302
    assert response.url == closed_opening.get_absolute_url()
    assert message_texts(response) == [
        "UX Researcher is closed, so it can't take new applications."
    ]


def test_the_create_page_refuses_a_candidate_with_nowhere_left_to_apply(
    client, recruiter, apply, ann, backend, closed_opening, indeed
):
    apply(ann, backend, indeed)  # the only open opening; the other is closed
    client.force_login(recruiter)

    response = client.get(f"{CREATE_URL}?candidate={ann.pk}")

    assert response.url == ann.get_absolute_url()
    assert message_texts(response) == ["There are no open openings Ann Lee hasn't applied for."]


def test_the_create_page_refuses_to_start_from_an_archived_candidate(
    client, recruiter, ann, backend
):
    Candidate.objects.filter(pk=ann.pk).update(is_archived=True, archived_at=timezone.now())
    client.force_login(recruiter)

    response = client.get(f"{CREATE_URL}?candidate={ann.pk}")

    assert response.url == ann.get_absolute_url()
    assert message_texts(response) == [
        "Ann Lee is archived, so they can't apply for anything. Unarchive them first."
    ]


def test_posting_a_closed_opening_directly_is_refused_and_writes_nothing(
    client, recruiter, ann, closed_opening, indeed
):
    client.force_login(recruiter)

    response = client.post(
        CREATE_URL, {"candidate": ann.pk, "opening": closed_opening.pk, "source": indeed.pk}
    )

    assert response.status_code == 200
    assert "Pick an open opening. Closed openings don&#x27;t take new applications." in (
        response.content.decode()
    )
    assert counts() == (0, 0)


def test_posting_a_duplicate_shows_the_friendly_error_and_writes_nothing(
    client, recruiter, apply, ann, backend, indeed
):
    apply(ann, backend, indeed)
    client.force_login(recruiter)

    response = client.post(
        CREATE_URL, {"candidate": ann.pk, "opening": backend.pk, "source": indeed.pk}
    )

    assert response.status_code == 200
    assert 'data-testid="error-opening"' in response.content.decode()
    assert "Ann Lee has already applied for Backend Developer." in response.content.decode()
    assert counts() == (1, 1)


def test_a_refusal_after_the_form_was_checked_is_shown_on_the_form(
    client, recruiter, monkeypatch, ann, backend, indeed
):
    def closed_meanwhile(**kwargs):
        raise ValidationError("Backend Developer is closed, so it can't take new applications.")

    monkeypatch.setattr("applications.views.record_application", closed_meanwhile)
    client.force_login(recruiter)

    response = client.post(
        CREATE_URL, {"candidate": ann.pk, "opening": backend.pk, "source": indeed.pk}
    )

    assert response.status_code == 200
    assert 'data-testid="form-errors"' in response.content.decode()
    assert counts() == (0, 0)


@pytest.mark.parametrize(("source_fixture", "shows"), [("referral", True), ("indeed", False)])
def test_htmx_source_change_returns_only_the_source_fields(
    client, recruiter, request, source_fixture, shows
):
    source = request.getfixturevalue(source_fixture)
    client.force_login(recruiter)

    response = client.get(
        CREATE_URL, {"source": source.pk}, HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER_NAME="source"
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "<html" not in content
    assert 'name="source"' in content
    assert ('name="referred_by"' in content) is shows
    assert "HX-Request" in response["Vary"]


def test_htmx_candidate_change_refills_the_source_from_that_candidate(
    client, recruiter, apply, ann, ben, backend, qa, indeed, linkedin
):
    apply(ben, backend, linkedin)
    client.force_login(recruiter)

    response = client.get(
        CREATE_URL,
        {"candidate": ben.pk, "opening": qa.pk, "source": indeed.pk},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER_NAME="candidate",
    )

    assert response.context["form"]["source"].value() == linkedin.pk


def test_htmx_refreshes_never_redirect_even_for_a_candidate_with_nowhere_to_apply(
    client, recruiter, apply, ann, backend, indeed
):
    apply(ann, backend, indeed)
    client.force_login(recruiter)

    response = client.get(
        CREATE_URL, {"candidate": ann.pk}, HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER_NAME="candidate"
    )

    assert response.status_code == 200
    assert "<html" not in response.content.decode()


def test_the_full_form_wires_candidate_and_source_to_htmx(client, recruiter, ann, backend):
    client.force_login(recruiter)

    content = client.get(f"{CREATE_URL}?candidate={ann.pk}").content.decode()

    assert content.count(f'hx-get="{CREATE_URL}"') == 2
    assert 'id="source-fields"' in content


# The edit form: an old application keeps showing its retired source.


@pytest.fixture
def old_application(apply, ann, backend, indeed, monster):
    """Ann's application, recorded through Monster before Monster was retired."""
    application = apply(ann, backend, indeed)
    Application.objects.filter(pk=application.pk).update(source=monster)
    application.refresh_from_db()
    return application


def test_an_old_applications_edit_form_shows_its_retired_source_selected(
    client, recruiter, old_application, monster
):
    client.force_login(recruiter)

    response = client.get(reverse("applications:update", args=[old_application.pk]))

    content = response.content.decode()
    assert (
        f'<option value="{monster.pk}" selected>Monster · Job board (retired)</option>' in content
    )
    assert 'data-testid="application-summary"' in content
    assert 'name="candidate"' not in content
    assert 'name="opening"' not in content


def test_saving_an_old_application_keeps_its_retired_source(
    client, recruiter, old_application, monster
):
    client.force_login(recruiter)

    response = client.post(
        reverse("applications:update", args=[old_application.pk]), {"source": monster.pk}
    )

    assert response.status_code == 302
    assert response.url == old_application.candidate.get_absolute_url()
    old_application.refresh_from_db()
    assert old_application.source == monster


def test_editing_from_the_opening_page_returns_there(client, recruiter, old_application, indeed):
    client.force_login(recruiter)
    url = reverse("applications:update", args=[old_application.pk]) + "?from=opening"

    response = client.post(url, {"source": indeed.pk})

    assert response.url == old_application.opening.get_absolute_url()


def test_htmx_on_the_edit_form_shows_referred_by_for_a_referral(
    client, recruiter, old_application, referral
):
    client.force_login(recruiter)

    response = client.get(
        reverse("applications:update", args=[old_application.pk]),
        {"source": referral.pk},
        HTTP_HX_REQUEST="true",
    )

    assert 'name="referred_by"' in response.content.decode()
    assert "<html" not in response.content.decode()
