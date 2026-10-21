import pandas as pd
from app.supportpilot.data_utils import prepare_dataframe, tags_for_row, top_tag_vocabulary
from app.supportpilot.policy import escalation_reason


def test_prepare_dataframe_combines_subject_and_body_and_preserves_unicode():
    source = pd.DataFrame({
        "subject": ["Fehler bei Verbindung"],
        "body": ["Die Verbindung schlägt fehl: Grüße!"],
        "queue": ["IT Support"], "type": ["Incident"], "priority": ["high"], "language": ["de"],
    })
    result = prepare_dataframe(source)
    assert "Fehler bei Verbindung" in result.loc[0, "text"]
    assert "Grüße" in result.loc[0, "text"]


def test_tags_for_row_deduplicates_and_skips_missing_values():
    row = pd.Series({"tag_1": "VPN", "tag_2": "Network", "tag_3": "VPN", "tag_4": None})
    assert tags_for_row(row) == ["VPN", "Network"]


def test_top_tag_vocabulary_orders_by_frequency():
    assert top_tag_vocabulary([["A", "B"], ["A"], ["B", "C"]], limit=2) == ["A", "B"]


def test_security_incident_triggers_escalation():
    reasons = escalation_reason("Possible data breach", "Unusual activity detected", {"label": "medium"}, {})
    assert "possible_security_incident" in reasons
