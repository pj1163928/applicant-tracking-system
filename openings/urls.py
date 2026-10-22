from django.urls import path

from applications.views import PipelineBoardView
from openings.views import (
    GracePeriodExtendView,
    GracePeriodSetView,
    OpeningCancelRemainingView,
    OpeningCloseView,
    OpeningCreateView,
    OpeningDetailView,
    OpeningListView,
    OpeningReopenView,
    OpeningRestoreView,
    OpeningSkillAttachView,
    OpeningSkillDetachView,
    OpeningUpdateView,
)

app_name = "openings"

urlpatterns = [
    path("", OpeningListView.as_view(), name="list"),
    path("new/", OpeningCreateView.as_view(), name="create"),
    path("<int:pk>/", OpeningDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", OpeningUpdateView.as_view(), name="update"),
    path("<int:pk>/close/", OpeningCloseView.as_view(), name="close"),
    path("<int:pk>/reopen/", OpeningReopenView.as_view(), name="reopen"),
    path("<int:pk>/restore/", OpeningRestoreView.as_view(), name="restore"),
    path(
        "<int:pk>/cancel-remaining/",
        OpeningCancelRemainingView.as_view(),
        name="cancel_remaining",
    ),
    path("<int:pk>/grace-period/", GracePeriodSetView.as_view(), name="grace_period"),
    path(
        "<int:pk>/grace-period/extend/",
        GracePeriodExtendView.as_view(),
        name="extend_grace_period",
    ),
    path("<int:pk>/skills/add/", OpeningSkillAttachView.as_view(), name="skill_attach"),
    path(
        "<int:pk>/skills/<int:skill_pk>/remove/",
        OpeningSkillDetachView.as_view(),
        name="skill_detach",
    ),
    # The board belongs to the applications app, but lives under its opening.
    path("<int:pk>/board/", PipelineBoardView.as_view(), name="board"),
]
