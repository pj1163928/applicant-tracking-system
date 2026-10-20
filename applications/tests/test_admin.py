"""The Django admin shows applications and stage history but can't change them."""

import pytest
from django.urls import reverse

from applications.models import Application, StageChange

pytestmark = pytest.mark.django_db


@pytest.fixture
def application(apply, ann, backend, indeed):
    return apply(ann, backend, indeed)


@pytest.mark.parametrize(
    ("model", "name"), [(Application, "application"), (StageChange, "stagechange")]
)
def test_the_admin_lists_and_shows_records_read_only(client, admin, application, model, name):
    record = model.objects.first()
    client.force_login(admin)

    assert client.get(reverse(f"admin:applications_{name}_changelist")).status_code == 200
    detail = client.get(reverse(f"admin:applications_{name}_change", args=[record.pk]))
    assert detail.status_code == 200
    assert 'name="_save"' not in detail.content.decode()


@pytest.mark.parametrize(
    ("model", "name"), [(Application, "application"), (StageChange, "stagechange")]
)
def test_the_admin_cannot_add_change_or_delete(client, admin, application, model, name):
    record = model.objects.first()
    client.force_login(admin)
    before = (Application.objects.count(), StageChange.objects.count())

    statuses = [
        client.get(reverse(f"admin:applications_{name}_add")).status_code,
        client.post(reverse(f"admin:applications_{name}_add"), {}).status_code,
        client.post(reverse(f"admin:applications_{name}_change", args=[record.pk]), {}).status_code,
        client.post(
            reverse(f"admin:applications_{name}_delete", args=[record.pk]), {"post": "yes"}
        ).status_code,
    ]

    assert statuses == [403, 403, 403, 403]
    assert (Application.objects.count(), StageChange.objects.count()) == before
    application.refresh_from_db()
    assert application.stage == Application.Stage.APPLIED
