from datetime import datetime
from datetime import timezone as dt_timezone

from integrations.agent.openrouter import TOOLS, build_system_prompt
from tenants.models import Tenant


def _tenant(**overrides):
    defaults = {
        "business_name": "Cedars Clinic",
        "vertical": Tenant.Vertical.DOCTOR,
        "timezone": "Asia/Beirut",
        "language_defaults": ["Arabic", "French"],
        "system_prompt_overrides": {},
    }
    defaults.update(overrides)

    return Tenant(**defaults)


def test_system_prompt_contains_tenant_identity():
    tenant = _tenant()

    prompt = build_system_prompt(tenant)

    assert "Cedars Clinic" in prompt
    assert "Doctor" in prompt
    assert "Asia/Beirut" in prompt
    assert "Arabic, French" in prompt


def test_system_prompt_includes_tenant_overrides():
    tenant = _tenant(
        system_prompt_overrides={
            "tone": "Warm and reassuring",
            "booking_note": "Do not offer Friday appointments",
        }
    )

    prompt = build_system_prompt(tenant)

    assert "- tone: Warm and reassuring" in prompt
    assert "- booking note: Do not offer Friday appointments" in prompt


def test_system_prompt_handles_nested_overrides():
    tenant = _tenant(
        system_prompt_overrides={
            "policies": {
                "emergency": "Ask the user to call the clinic",
            }
        }
    )

    prompt = build_system_prompt(tenant)

    assert "emergency" in prompt
    assert "Ask the user to call the clinic" in prompt


def test_tool_schema_names_are_complete():
    assert {tool["name"] for tool in TOOLS} == {
        "check_availability",
        "create_booking",
        "ask_clarification",
    }


def test_check_availability_schema_describes_date_and_time():
    tool = next(tool for tool in TOOLS if tool["name"] == "check_availability")

    properties = tool["input_schema"]["properties"]

    assert "date" in properties
    assert "time_preference" in properties


def test_create_booking_schema_requires_booking_details():
    tool = next(tool for tool in TOOLS if tool["name"] == "create_booking")

    assert set(tool["input_schema"]["required"]) == {
        "service_name",
        "slot_start",
        "slot_end",
    }


def test_clarification_schema_requires_text():
    tool = next(tool for tool in TOOLS if tool["name"] == "ask_clarification")

    assert tool["input_schema"]["required"] == ["text"]


def test_system_prompt_includes_current_local_weekday(
    monkeypatch,
):
    fixed_now = datetime(
        2026,
        10,
        8,
        8,
        0,
        tzinfo=dt_timezone.utc,
    )

    monkeypatch.setattr(
        "integrations.agent.openrouter.timezone.now",
        lambda: fixed_now,
    )

    tenant = _tenant()
    prompt = build_system_prompt(tenant)

    assert "Current local date: 2026-10-08." in prompt
    assert "Current local weekday: Thursday." in prompt


def test_system_prompt_includes_pending_booking_state():
    tenant = _tenant()

    prompt = build_system_prompt(
        tenant,
        pending_intent_state={
            "intent": "booking",
            "service_name": "Consultation",
            "date": "2026-10-12",
            "time_preference": "afternoon",
        },
    )

    assert "CURRENT BOOKING STATE" in prompt
    assert '"intent": "booking"' in prompt
    assert '"service_name": "Consultation"' in prompt
    assert '"date": "2026-10-12"' in prompt
    assert '"time_preference": "afternoon"' in prompt
