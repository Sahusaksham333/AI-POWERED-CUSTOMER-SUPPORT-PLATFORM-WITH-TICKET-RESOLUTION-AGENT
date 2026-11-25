"""Pure-function tests for the modular M3 specialist agents."""
from app.supportpilot.m3.agents.diagnosis import missing_information, route_team
from app.supportpilot.m3.agents.policy import detect_risks
from app.supportpilot.m3.agents.resolution import run_resolution
from app.supportpilot.m3.agents.validation import run_validation


def test_risk_scanner_detects_multiple_high_risk_signals():
    flags = detect_risks("Possible ransomware and smoke from the swollen battery")
    assert "possible_security_incident" in flags
    assert "physical_safety_risk" in flags


def test_team_routing_prioritises_safety_and_security():
    assert route_team("Network Support", ["possible_security_incident"]) == "Security / Safety Response"
    assert route_team("Network Connectivity", []) == "Network Support"


def test_diagnosis_requests_missing_context():
    questions = missing_information("VPN unavailable", "It is not working", "Network Support")
    assert any("error message" in question.lower() for question in questions)
    assert any("first start" in question.lower() for question in questions)


def test_resolution_does_not_call_llm_without_sources():
    class Generator:
        def draft(self, **kwargs):
            raise AssertionError("LLM must not be called without retrieved sources")

    class Pipeline:
        generator = Generator()

    result = run_resolution(Pipeline(), "VPN", "No connection", "auto", {}, [])
    assert result["generated"] is False
    assert result["draft"] is None
    assert "no approved knowledge source" in result["generation_error"]


def test_validation_requires_review_without_evidence():
    result = run_validation("Try restarting the client", [], [])
    assert result["requires_human_approval"] is True
    assert "no_retrieved_evidence" in result["unsafe_findings"]
