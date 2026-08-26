from django.urls import reverse


def test_healthcheck(client):
    response = client.get(reverse("healthcheck"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
