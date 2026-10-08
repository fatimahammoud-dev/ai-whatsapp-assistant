import pytest
from django.core.exceptions import ImproperlyConfigured

from integrations.agent.mock import MockAgent
from integrations.agent.openrouter import OpenRouterAgent
from integrations.tasks import _get_agent


def test_get_agent_returns_mock_agent(settings):
    settings.AGENT_BACKEND = "mock"

    agent = _get_agent()

    assert isinstance(agent, MockAgent)


def test_get_agent_returns_openrouter_agent(settings):
    settings.AGENT_BACKEND = "openrouter"
    settings.OPENROUTER_API_KEY = "test-api-key"
    settings.OPENROUTER_MODEL = "test/model"

    agent = _get_agent()

    assert isinstance(agent, OpenRouterAgent)


def test_get_agent_rejects_unknown_backend(settings):
    settings.AGENT_BACKEND = "unknown"

    with pytest.raises(ImproperlyConfigured):
        _get_agent()
