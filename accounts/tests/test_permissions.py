import pytest
from django.contrib.auth.models import AnonymousUser, Group

from accounts.permissions import (
    can_be_designated_authority,
    can_make_offer,
    can_manage_applications,
    can_manage_candidates,
    can_manage_opening_skills,
    can_manage_openings,
    can_manage_sources,
    can_move_applications,
    can_retire_skills,
    eligible_authorities,
)
from accounts.roles import HIRING_MANAGER, INTERVIEWER, RECRUITER
from openings.models import JobOpening

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("user_fixture", "expected"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", False),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_can_manage_candidates_by_role(request, user_fixture, expected):
    assert can_manage_candidates(request.getfixturevalue(user_fixture)) is expected


def test_inactive_recruiter_cannot_manage_candidates(recruiter):
    recruiter.is_active = False

    assert can_manage_candidates(recruiter) is False


def test_anonymous_user_cannot_manage_candidates():
    assert can_manage_candidates(AnonymousUser()) is False


@pytest.mark.parametrize(
    ("user_fixture", "expected"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", False),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_can_manage_sources_by_role(request, user_fixture, expected):
    assert can_manage_sources(request.getfixturevalue(user_fixture)) is expected


def test_inactive_or_anonymous_users_cannot_manage_sources(recruiter):
    recruiter.is_active = False

    assert can_manage_sources(recruiter) is False
    assert can_manage_sources(AnonymousUser()) is False


@pytest.fixture
def inactive_manager(make_user):
    return make_user("gone-manager", HIRING_MANAGER, is_active=False)


@pytest.fixture
def inactive_admin(make_user):
    return make_user("gone-admin", is_superuser=True, is_active=False)


@pytest.mark.parametrize(
    ("user_fixture", "eligible"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", True),
        ("interviewer", False),
        ("no_role_user", False),
        ("inactive_manager", False),
        ("inactive_admin", False),
    ],
)
def test_only_active_admins_recruiters_and_hiring_managers_can_be_designated_authority(
    request, user_fixture, eligible
):
    user = request.getfixturevalue(user_fixture)

    assert can_be_designated_authority(user) is eligible
    # The picker's list agrees with the rule, so the form can only offer and accept eligible staff.
    assert eligible_authorities().filter(pk=user.pk).exists() is eligible


def test_anonymous_user_cannot_be_designated_authority():
    assert can_be_designated_authority(AnonymousUser()) is False


def test_eligible_authorities_lists_a_user_in_two_groups_once(make_user):
    both = make_user("both", RECRUITER)
    both.groups.add(Group.objects.get(name=HIRING_MANAGER))

    assert list(eligible_authorities()) == [both]


@pytest.mark.parametrize(
    ("user_fixture", "expected"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", True),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_can_manage_openings_by_role(request, user_fixture, expected):
    assert can_manage_openings(request.getfixturevalue(user_fixture)) is expected


def test_inactive_or_anonymous_users_cannot_manage_openings(hiring_manager):
    hiring_manager.is_active = False

    assert can_manage_openings(hiring_manager) is False
    assert can_manage_openings(AnonymousUser()) is False


@pytest.mark.parametrize(
    ("user_fixture", "expected"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", False),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_can_manage_applications_by_role(request, user_fixture, expected):
    assert can_manage_applications(request.getfixturevalue(user_fixture)) is expected


def test_inactive_or_anonymous_users_cannot_manage_applications(recruiter):
    recruiter.is_active = False
    recruiter.save()

    assert can_manage_applications(recruiter) is False
    assert can_manage_applications(AnonymousUser()) is False


@pytest.mark.parametrize(
    ("user_fixture", "expected"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", True),
        ("interviewer", False),
        ("no_role_user", False),
        ("inactive_manager", False),
        ("inactive_admin", False),
    ],
)
def test_can_move_applications_by_role(request, user_fixture, expected):
    assert can_move_applications(request.getfixturevalue(user_fixture)) is expected


def test_anonymous_user_cannot_move_applications():
    assert can_move_applications(AnonymousUser()) is False


@pytest.fixture
def riley(make_user):
    """A Recruiter who is the designated authority of ``rileys_opening``."""
    return make_user("riley", RECRUITER, first_name="Riley", last_name="Chen")


@pytest.fixture
def rileys_opening(make_opening, riley):
    return make_opening("Support Specialist", riley)


@pytest.mark.parametrize(
    ("user_fixture", "expected"),
    [
        ("admin", True),
        ("hiring_manager", True),
        ("recruiter", False),  # a Recruiter, but not this opening's authority
        ("interviewer", False),
        ("no_role_user", False),
        ("inactive_manager", False),
        ("inactive_admin", False),
    ],
)
def test_can_make_offer_by_role_on_someone_elses_opening(
    request, user_fixture, expected, rileys_opening
):
    assert can_make_offer(request.getfixturevalue(user_fixture), rileys_opening) is expected


def test_the_designated_authority_can_make_offers_on_their_own_opening_only(
    riley, rileys_opening, make_opening, hiring_manager
):
    closed = make_opening("Data Engineer", riley, status=JobOpening.Status.CLOSED)
    someone_elses = make_opening("Backend Developer", hiring_manager)

    assert can_make_offer(riley, rileys_opening) is True
    # Closing an opening doesn't stop offers on the applications already in progress.
    assert can_make_offer(riley, closed) is True
    assert can_make_offer(riley, someone_elses) is False


def make_inactive(user):
    user.is_active = False
    user.save()


def make_interviewer(user):
    user.groups.set([Group.objects.get(name=INTERVIEWER)])


def remove_roles(user):
    user.groups.clear()


@pytest.mark.parametrize("change", [make_inactive, make_interviewer, remove_roles])
def test_a_designated_authority_who_is_no_longer_eligible_cannot_make_offers(
    change, riley, rileys_opening
):
    change(riley)

    assert can_make_offer(riley, rileys_opening) is False


def test_elevated_flags_or_move_rights_never_stand_in_for_offer_authority(
    recruiter, make_user, rileys_opening
):
    # A Recruiter may move stages, and Django admin access (is_staff) is not the Admin role.
    recruiter.is_staff = True
    recruiter.save()
    staff_without_role = make_user("staff-only", is_staff=True)

    assert can_make_offer(recruiter, rileys_opening) is False
    assert can_make_offer(staff_without_role, rileys_opening) is False
    assert can_make_offer(AnonymousUser(), rileys_opening) is False


@pytest.fixture
def riley_demoted(riley):
    """Riley, still named as ``rileys_opening``'s authority, but now only an Interviewer."""
    make_interviewer(riley)
    return riley


@pytest.mark.parametrize(
    ("user_fixture", "manages_own", "manages_elsewhere", "retires_skills"),
    [
        ("admin", True, True, True),
        ("hiring_manager", True, True, True),
        # Riley is the authority of rileys_opening only: she manages its skills,
        # no other opening's, and never retires a skill.
        ("riley", True, False, False),
        ("recruiter", False, False, False),  # a Recruiter, but not this opening's authority
        ("riley_demoted", False, False, False),  # named as authority, but no longer eligible
        ("interviewer", False, False, False),
        ("no_role_user", False, False, False),
        ("inactive_manager", False, False, False),
        ("inactive_admin", False, False, False),
    ],
)
def test_who_may_manage_an_openings_skills_and_who_may_retire_skills(
    request,
    user_fixture,
    manages_own,
    manages_elsewhere,
    retires_skills,
    rileys_opening,
    make_opening,
    make_user,
):
    someone_elses = make_opening("Backend Developer", make_user("other-manager", HIRING_MANAGER))
    user = request.getfixturevalue(user_fixture)

    assert can_manage_opening_skills(user, rileys_opening) is manages_own
    assert can_manage_opening_skills(user, someone_elses) is manages_elsewhere
    assert can_retire_skills(user) is retires_skills
