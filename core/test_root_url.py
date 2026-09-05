import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_root_url_redirects_to_dashboard(client):
    response = client.get("/")

    assert response.status_code == 302
    assert response.url == reverse("dashboard")


@pytest.mark.django_db
def test_root_url_sends_anonymous_visitors_to_login(client):
    response = client.get("/", follow=True)

    assert response.status_code == 200
    assert response.redirect_chain[-1][0].startswith(reverse("login"))
