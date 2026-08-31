import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


@pytest.mark.django_db
def test_login_page_loads(client):
    response = client.get(reverse("login"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_staff_user_can_log_in(client):
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="staff_test",
        password="test-password-123",
    )

    response = client.post(
        reverse("login"),
        {
            "username": user.username,
            "password": "test-password-123",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("dashboard")


@pytest.mark.django_db
def test_dashboard_requires_login(client):
    response = client.get(reverse("dashboard"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_logout_ends_session(client):
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="logout_test",
        password="test-password-123",
    )

    client.force_login(user)

    response = client.post(reverse("logout"))

    assert response.status_code == 302
    assert response.url == reverse("login")

    dashboard_response = client.get(reverse("dashboard"))
    assert dashboard_response.status_code == 302
