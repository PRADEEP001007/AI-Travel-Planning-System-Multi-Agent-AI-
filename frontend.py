import os
import html
import uuid
from datetime import datetime

import streamlit as st
from langchain_core.messages import HumanMessage

from main import app

st.set_page_config(page_title="Trip planner", page_icon="✈️", layout="centered")

# ---------------------------------------------------------------------------
# Style: dark mode. Black page, white text, grey rules.
# The one memorable element is the boarding-pass summary strip.
# ---------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

:root {
    --ink: #FFFFFF;
    --paper: #000000;
    --sign: #000000;
    --stub: #141414;
    --teal: #FFFFFF;
    --rule: #3A3A3A;
    --muted: #A8A8A8;
}

html, body, .stApp, .stMarkdown, input, textarea, label, button {
    font-family: 'IBM Plex Sans', sans-serif;
    color: var(--ink);
}
.stApp { background: var(--paper); }
#MainMenu, footer, header { visibility: hidden; }
.block-container { max-width: 860px; padding-top: 2.2rem; }

h1.app-title {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-weight: 700;
    font-size: 2.5rem;
    line-height: 1.1;
    margin: 0 0 0.4rem;
    letter-spacing: -0.01em;
}
p.app-sub { color: var(--muted); max-width: 52ch; margin: 0 0 1.6rem; }

/* Form */
[data-testid="stForm"] {
    background: #0A0A0A;
    border: 1px solid #666666;
    border-radius: 10px;
    padding: 1.4rem 1.4rem 1rem;
}
[data-testid="stForm"] label p { font-weight: 500; font-size: 0.9rem; }

/* Primary button */
[data-testid="stFormSubmitButton"] button {
    background: var(--ink);
    color: var(--sign);
    border: 0;
    border-radius: 6px;
    font-weight: 600;
    padding: 0.7rem 1.2rem;
    width: 100%;
}
[data-testid="stFormSubmitButton"] button:hover { background: #D9D9D9; color: var(--sign); }
[data-testid="stFormSubmitButton"] button:focus-visible,
input:focus-visible, textarea:focus-visible {
    outline: 3px solid var(--teal);
    outline-offset: 2px;
}

/* Boarding-pass summary strip */
.ticket {
    display: flex;
    background: #0A0A0A;
    border: 1px solid #666666;
    border-radius: 10px;
    overflow: hidden;
    margin: 1.6rem 0 1rem;
}
.ticket .route {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 1.1rem;
    padding: 1.1rem 1.4rem;
    flex-wrap: wrap;
}
.ticket .city {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 1.9rem;
    font-weight: 700;
    line-height: 1.1;
}
.ticket .tag { font-size: 0.8rem; color: var(--muted); }
.ticket .arrow { font-size: 1.6rem; color: var(--teal); }
.ticket .stub {
    background: var(--stub);
    border-left: 2px dashed var(--ink);
    padding: 1.1rem 1.4rem;
    display: flex;
    gap: 1.6rem;
    align-items: center;
}
.ticket .stub b { display: block; font-size: 1.15rem; }
.ticket .stub span { font-size: 0.8rem; color: var(--muted); }
@media (max-width: 640px) {
    .ticket { flex-direction: column; }
    .ticket .stub { border-left: 0; border-top: 2px dashed var(--ink); }
}

/* Tabs and download */
.stTabs [data-baseweb="tab"] { font-weight: 500; }
.stTabs [aria-selected="true"] { color: var(--teal); }
div[data-testid="stDownloadButton"] button {
    border: 1px solid var(--ink);
    border-radius: 6px;
    background: #0A0A0A;
}
.note { color: var(--muted); font-size: 0.88rem; }

/* ---- Readability fix: force readable colours whatever theme the browser/Streamlit uses ---- */
:root { color-scheme: dark; }
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background: var(--paper) !important;
    color: var(--ink) !important;
}

/* All normal text */
.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown td, .stMarkdown th,
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4,
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] * {
    color: var(--ink) !important;
}
.stMarkdown strong { color: var(--ink) !important; }
p.app-sub, .note, .note * { color: var(--muted) !important; }

/* Field labels and help icons */
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] *,
label, label p, label span { color: var(--ink) !important; }
[data-testid="stTooltipIcon"] svg { color: var(--muted) !important; fill: var(--muted) !important; }

/* Inputs: white box, dark text */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"] {
    background: #0A0A0A !important;
    border-radius: 6px !important;
}
[data-baseweb="input"], [data-baseweb="textarea"] { border: 1px solid #666666 !important; }
input, textarea {
    background: #0A0A0A !important;
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
    caret-color: var(--ink) !important;
}
input::placeholder, textarea::placeholder {
    color: #9A9A9A !important;
    -webkit-text-fill-color: #9A9A9A !important;
    opacity: 1 !important;
}
[data-testid="InputInstructions"], [data-testid="InputInstructions"] * { color: var(--muted) !important; }
[data-testid="stNumberInput"] button {
    background: #222222 !important;
    color: var(--ink) !important;
}
[data-testid="stNumberInput"] button svg { fill: var(--ink) !important; color: var(--ink) !important; }

/* Sidebar */
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {
    background: #0A0A0A !important;
    border-right: 1px solid var(--rule);
}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] span,
[data-testid="stSidebar"] label, [data-testid="stSidebar"] div { color: var(--ink) !important; }
[data-testid="stSidebar"] .note, [data-testid="stSidebar"] .note * { color: var(--muted) !important; }
[data-testid="stSidebar"] hr { border-color: var(--rule) !important; }
[data-testid="stSidebarCollapseButton"] svg, [data-testid="stExpandSidebarButton"] svg {
    color: var(--ink) !important; fill: var(--ink) !important;
}

/* Tabs */
.stTabs [data-baseweb="tab"], .stTabs [data-baseweb="tab"] p { color: var(--muted) !important; }
.stTabs [aria-selected="true"], .stTabs [aria-selected="true"] p { color: var(--teal) !important; }

/* Tab underline and focus ring in black */
.stTabs [data-baseweb="tab-highlight"] { background: var(--ink) !important; }
.stTabs [aria-selected="true"], .stTabs [aria-selected="true"] p { font-weight: 600 !important; }

/* Progress box, alerts, plain text blocks */
[data-testid="stStatus"], [data-testid="stExpander"] details {
    background: #0A0A0A !important;
    border: 1px solid var(--rule) !important;
    border-radius: 10px !important;
}
[data-testid="stStatus"] *, [data-testid="stExpander"] * { color: var(--ink) !important; }
[data-testid="stAlert"] { background: #1A1A1A !important; border-radius: 8px !important; }
[data-testid="stAlert"] * { color: var(--ink) !important; }
[data-testid="stText"], [data-testid="stText"] * {
    color: var(--ink) !important;
    background: #0A0A0A !important;
}
[data-testid="stText"] {
    border: 1px solid var(--rule);
    border-radius: 8px;
    padding: 0.8rem 1rem;
    white-space: pre-wrap;
}

/* Tables in the plan */
.stMarkdown table { border-collapse: collapse; width: 100%; background: #0A0A0A; }
.stMarkdown th { background: #1A1A1A !important; }
.stMarkdown th, .stMarkdown td { border: 1px solid var(--rule) !important; padding: 0.45rem 0.6rem !important; }

/* Buttons */
[data-testid="stFormSubmitButton"] button, [data-testid="stFormSubmitButton"] button * {
    color: var(--sign) !important;
}
div[data-testid="stDownloadButton"] button,
div[data-testid="stDownloadButton"] button * {
    color: var(--ink) !important;
    background: #0A0A0A !important;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def md(text: str) -> str:
    """Escape $ so Streamlit does not treat prices as math."""
    return (text or "").replace("$", r"\$")


STEP_LABELS = {
    "parse_agent": "Read your request",
    "flight_agent": "Checked flights",
    "hotel_agent": "Found hotels",
    "itinerary_agent": "Drafted the itinerary",
    "final_agent": "Reviewed the plan",
}

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("**Session**")
    keep_history = st.toggle(
        "Remember my past trips",
        value=False,
        help="Off: every plan starts fresh. On: plans are saved under your name.",
    )
    user_id = st.text_input("Your name", value="aarohi_user", disabled=not keep_history)
    st.markdown("---")
    st.markdown(
        "<p class='note'>Flights come from a schedule service, so fares are "
        "estimates. Hotel prices come from web search. Check both before "
        "booking.</p>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Header + form
# ---------------------------------------------------------------------------
st.markdown("<h1 class='app-title'>Trip planner</h1>", unsafe_allow_html=True)
st.markdown(
    "<p class='app-sub'>Tell us where you are going and what you can spend. "
    "You get flights, a stay and a day-by-day plan that fits your budget.</p>",
    unsafe_allow_html=True,
)

with st.form("trip"):
    c1, c2 = st.columns(2)
    origin = c1.text_input("From", value="Chennai")
    destination = c2.text_input("To", placeholder="Delhi, Goa, Japan, Singapore")

    c3, c4, c5 = st.columns(3)
    days = c3.number_input("Days", min_value=1, max_value=30, value=3)
    travellers = c4.number_input("Travellers", min_value=1, max_value=12, value=2)
    budget = c5.number_input("Total budget (₹)", min_value=1000, value=100000, step=5000)

    notes = st.text_area(
        "Anything else we should know? (optional)",
        placeholder="Vegetarian food, no early mornings, travelling with parents",
        height=80,
    )
    submitted = st.form_submit_button("Plan my trip")

# ---------------------------------------------------------------------------
# Run the agents
# ---------------------------------------------------------------------------
if submitted:
    if not destination.strip():
        st.warning("Add a destination so we know where to plan.")
    else:
        query = (
            f"Plan a {days} days {destination.strip()} trip from {origin.strip()} "
            f"for {travellers} people under {budget} rupees."
        )
        if notes.strip():
            query += f" Extra requests: {notes.strip()}"

        thread_id = (
            f"{user_id}" if keep_history else f"trip_{uuid.uuid4()}"
        )
        config = {"configurable": {"thread_id": thread_id}}

        result = {
            "origin": origin.strip(),
            "destination": destination.strip(),
            "days": int(days),
            "travellers": int(travellers),
            "budget": int(budget),
            "flights": "",
            "hotels": "",
            "plan": "",
            "llm_calls": 0,
            "query": query,
        }

        try:
            with st.status("Planning your trip", expanded=True) as status:
                for chunk in app.stream(
                    {
                        "messages": [HumanMessage(content=query)],
                        "user_query": query,
                        "origin": origin.strip(),
                        "destination": destination.strip(),
                        "days": int(days),
                        "travellers": int(travellers),
                        "budget_inr": int(budget),
                        "flight_results": "",
                        "hotel_results": "",
                        "itinerary": "",
                        "llm_calls": 0,
                    },
                    config=config,
                    stream_mode="updates",
                ):
                    for node, upd in chunk.items():
                        st.write(f"✓ {STEP_LABELS.get(node, node)}")
                        if node == "flight_agent":
                            result["flights"] = upd.get("flight_results", "")
                        elif node == "hotel_agent":
                            result["hotels"] = upd.get("hotel_results", "")
                        elif node == "final_agent":
                            msgs = upd.get("messages", [])
                            result["plan"] = msgs[-1].content if msgs else ""
                        result["llm_calls"] = max(
                            result["llm_calls"], upd.get("llm_calls", 0)
                        )
                status.update(label="Your plan is ready", state="complete", expanded=False)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result["file_name"] = f"travel_plan_{stamp}.md"
            result["file_content"] = (
                f"# Trip plan: {result['origin']} to {result['destination']}\n\n"
                f"**Request:** {result['query']}\n"
                f"**Generated:** {datetime.now():%Y-%m-%d %H:%M}\n\n---\n\n"
                f"{result['plan']}\n\n---\n\n## Flight data\n"
                f"{result['flights'] or 'N/A'}\n\n## Hotel data\n"
                f"{result['hotels'] or 'N/A'}\n"
            )
            save_dir = os.path.join(os.path.dirname(__file__), "travel_plans")
            os.makedirs(save_dir, exist_ok=True)
            with open(os.path.join(save_dir, result["file_name"]), "w", encoding="utf-8") as f:
                f.write(result["file_content"])
            st.session_state["result"] = result
        except Exception as e:
            st.error(
                f"Planning stopped before it finished: {e}. "
                "Check your API keys and database connection, then try again."
            )

# ---------------------------------------------------------------------------
# Show the result (kept in session so downloads and tab clicks do not wipe it)
# ---------------------------------------------------------------------------
res = st.session_state.get("result")

if res:
    esc = html.escape
    st.markdown(
        f"""
        <div class="ticket">
          <div class="route">
            <div><div class="city">{esc(res['origin'])}</div><div class="tag">From</div></div>
            <div class="arrow">→</div>
            <div><div class="city">{esc(res['destination'])}</div><div class="tag">To</div></div>
          </div>
          <div class="stub">
            <div><b>{res['days']}</b><span>days</span></div>
            <div><b>{res['travellers']}</b><span>travellers</span></div>
            <div><b>₹{res['budget']:,}</b><span>budget</span></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not res["plan"]:
        st.warning("The planner did not return a plan. Try again in a moment.")
    else:
        tab_plan, tab_flights, tab_hotels = st.tabs(["Plan", "Flights", "Hotels"])

        with tab_plan:
            st.markdown(md(res["plan"]))

        with tab_flights:
            if res["flights"]:
                st.text(res["flights"])
            else:
                st.info("No flight data was returned for this route.")

        with tab_hotels:
            if res["hotels"]:
                st.markdown(md(res["hotels"]))
            else:
                st.info("No hotel data was returned for this destination.")

        st.download_button(
            "Download plan",
            data=res["file_content"],
            file_name=res["file_name"],
            mime="text/markdown",
        )
        st.markdown(
            f"<p class='note'>Saved to travel_plans/{res['file_name']} · "
            f"{res['llm_calls']} model calls</p>",
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        "<p class='note'>Your plan will appear here after you press Plan my trip.</p>",
        unsafe_allow_html=True,
    )