import pytest
from django.core.exceptions import ImproperlyConfigured

from integrations.agent.claude import ClaudeAgent
from integrations.agent.mock import MockAgent
from integrations.tasks import _get_agent


def test_get_agent_returns_mock_agent(settings):
    settings.AGENT_BACKEND = "mock"

    agent = _get_agent()

    assert isinstance(agent, MockAgent)


def test_get_agent_returns_claude_agent(settings):
    settings.AGENT_BACKEND = "claude"
    settings.ANTHROPIC_API_KEY = "test-api-key"

    agent = _get_agent()

    assert isinstance(agent, ClaudeAgent)


def test_get_agent_rejects_unknown_backend(settings):
    settings.AGENT_BACKEND = "unknown"

    with pytest.raises(ImproperlyConfigured):
        _get_agent()
