"""Streamlit UI for the SupportPilot local API."""
from __future__ import annotations
import os
import requests
import pandas as pd
import streamlit as st

API_URL = os.getenv("SUPPORTPILOT_API_URL", "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(page_title="SupportPilot", page_icon="🎫", layout="wide")
st.title("SupportPilot")
st.caption("Multilingual AI ticket classification, evidence retrieval, and response drafting")

try:
    health_resp = requests.get(f"{API_URL}/health", timeout=4)
    health_resp.raise_for_status()
    health = health_resp.json()
    st.caption(f"API status: {health.get('status', 'unknown')} · {API_URL}")
except requests.RequestException:
    st.error(f"SupportPilot API is unavailable at {API_URL}. Start it with: `uvicorn app.main:app --reload`")
    st.stop()

new_tab, analytics_tab, system_tab = st.tabs(["New ticket", "Analytics", "System status"])
with new_tab:
    with st.form("ticket_form"):
        subject = st.text_input("Ticket subject", placeholder="VPN connection fails after sign-in")
        body = st.text_area("Ticket description", height=190, placeholder="Describe the symptoms, affected users, error messages, and steps already attempted.")
        language = st.selectbox("Ticket language", ["auto", "en", "de"])
        action = st.radio("Action", ["Classify ticket", "Draft troubleshooting response"], horizontal=True)
        submitted = st.form_submit_button("Process ticket", type="primary")
    if submitted:
        if len(subject.strip()) < 3 or len(body.strip()) < 5:
            st.warning("Enter a subject of at least 3 characters and a description of at least 5 characters.")
        else:
            endpoint = "/tickets/predict" if action == "Classify ticket" else "/tickets/resolve"
            try:
                with st.spinner("Processing ticket..."):
                    response = requests.post(f"{API_URL}{endpoint}", json={"subject": subject, "body": body, "language": language}, timeout=200)
                response.raise_for_status()
                result = response.json()
                st.subheader("Ticket analysis")
                cols = st.columns(4)
                for col, key in zip(cols, ["queue", "type", "priority"]):
                    pred = result.get("predictions", {}).get(key, {})
                    with col:
                        st.metric(key.title(), pred.get("label") or "Not trained")
                        if pred.get("confidence") is not None:
                            st.caption(f"Confidence: {pred['confidence']:.1%}")
                with cols[3]:
                    st.metric("Escalation", "Required" if result.get("escalated") else "Not flagged")
                if result.get("escalation_reasons"):
                    st.warning("Escalation flags: " + ", ".join(result["escalation_reasons"]))
                if result.get("tags"):
                    st.write("**Predicted tags:**", ", ".join(f"{x['tag']} ({x['confidence']:.2f})" for x in result["tags"]))
                if result.get("response_draft"):
                    st.subheader("Response draft — human review required")
                    st.text_area("Draft", value=result["response_draft"], height=250)
                    if result.get("sources"):
                        st.subheader("Retrieved knowledge sources")
                        for source in result["sources"]:
                            with st.expander(f"{source['source']} · chunk {source.get('chunk')} · distance {source.get('distance')}"):
                                st.write(source["text"])
                    if result.get("generation_error"):
                        st.warning(f"LLM generation issue: {result['generation_error']}")
                st.caption(f"Ticket ID: {result['ticket_id']}")
            except requests.RequestException as exc:
                st.error(f"Ticket processing failed: {exc}")

with analytics_tab:
    if st.button("Refresh analytics"):
        st.rerun()
    try:
        response = requests.get(f"{API_URL}/analytics", timeout=8)
        response.raise_for_status()
        metrics = response.json()
        c1, c2 = st.columns(2)
        c1.metric("Tickets processed", metrics["total_tickets"])
        c2.metric("Flagged for escalation", metrics["escalated_tickets"])
        left, right = st.columns(2)
        with left:
            st.write("**Queue distribution**")
            st.dataframe(pd.DataFrame(metrics.get("queues", [])), use_container_width=True, hide_index=True)
        with right:
            st.write("**Priority distribution**")
            st.dataframe(pd.DataFrame(metrics.get("priorities", [])), use_container_width=True, hide_index=True)
        st.write("**Recent tickets**")
        st.dataframe(pd.DataFrame(metrics.get("recent_tickets", [])), use_container_width=True, hide_index=True)
    except requests.RequestException as exc:
        st.error(f"Could not load analytics: {exc}")

with system_tab:
    services = health.get("services", {})
    st.write("**Classifier artifacts**")
    st.json(services.get("classifier", {}))
    st.write("**Knowledge retrieval**")
    st.json(services.get("retriever", {}))
    st.write("**Ollama**")
    st.json(services.get("ollama", {}))
    st.info("For GPU memory stability on an 8 GB RTX 4060, classifier inference defaults to CPU so Gemma can use the GPU. Benchmark GPU classifier inference separately before changing SUPPORTPILOT_CLASSIFIER_DEVICE.")
