import pytest
from django.contrib.auth.models import Group

from accounts.roles import ROLE_GROUPS


@pytest.mark.django_db
def test_role_groups_exist_after_migrate():
    assert set(Group.objects.values_list("name", flat=True)) >= set(ROLE_GROUPS)
    assert set(ROLE_GROUPS) == {"Recruiter", "Hiring Manager", "Interviewer"}
