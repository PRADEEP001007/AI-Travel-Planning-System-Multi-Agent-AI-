import os
import re
import json
import uuid
import operator
from typing import TypedDict, Annotated

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from langchain_groq import ChatGroq

from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# ---------------------------------------------------------------------------
# LLM
# llama-3.3-70b-versatile was retired by Groq on 2026-08-16.
# Override with GROQ_MODEL in .env if you want a different model.
# max_tokens is high so the answer is not cut off (reasoning tokens count too).
# ---------------------------------------------------------------------------
llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    max_tokens=8000,
    temperature=0.3,
)

MAX_TOOL_CHARS = 6000  # keep tool output small so we stay within token limits


def _clip(text) -> str:
    text = str(text)
    return text[:MAX_TOOL_CHARS]


def _drop_stale(text: str, max_years: int = 1) -> str:
    """Remove search results that say they are N years old (e.g. '18 years ago')."""
    entries = re.split(r"\n(?=[^\n]*https?://)", text)
    kept = []
    for e in entries:
        m = re.search(r"\b(\d+)\s+years?\s+ago", e, re.IGNORECASE)
        if m and int(m.group(1)) > max_years:
            continue
        kept.append(e)
    return "\n".join(kept)


def _to_int(value, default=0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class TravelState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    origin: str
    travellers: int
    destination: str
    days: int
    budget_inr: int
    flight_results: str
    hotel_results: str
    itinerary: str
    llm_calls: int


# ---------------------------------------------------------------------------
# Parse Agent: pull destination / days / budget out of the free-text request
# ---------------------------------------------------------------------------
def parse_agent(state: TravelState):
    query = state["user_query"]

    prompt = f"""Extract trip details from this request.
Reply with ONLY a JSON object (no markdown, no explanation) with these keys:
  "destination": string (country or city),
  "days": integer (number of days, 0 if not stated),
  "budget_inr": integer (total budget in Indian rupees; 1 lakh = 100000; 0 if not stated),
  "origin": string (departure city if mentioned, otherwise empty string),
  "travellers": integer (number of people travelling, 0 if not stated)

Request: {query}"""

    details = {}
    try:
        raw = llm.invoke([HumanMessage(content=prompt)]).content
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            details = json.loads(match.group(0))
    except Exception:
        details = {}

    # Values passed in directly (for example from the UI form) win over parsed ones
    destination = (
        state.get("destination")
        or str(details.get("destination") or "").strip()
        or query
    )
    days = state.get("days") or _to_int(details.get("days"), 0)
    budget = state.get("budget_inr") or _to_int(details.get("budget_inr"), 0)

    # Regex fallbacks if the LLM parse failed
    if days == 0:
        m = re.search(r"(\d+)\s*[- ]?\s*days?", query, re.IGNORECASE)
        days = int(m.group(1)) if m else 7
    if budget == 0:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs)", query, re.IGNORECASE)
        if m:
            budget = int(float(m.group(1)) * 100000)

    # Origin / travellers: keep anything passed in, else use what was parsed,
    # else fall back to defaults (set DEFAULT_ORIGIN in .env to change).
    origin = (
        state.get("origin")
        or str(details.get("origin") or "").strip()
        or os.getenv("DEFAULT_ORIGIN", "Chennai")
    )
    travellers = (
        state.get("travellers")
        or _to_int(details.get("travellers"), 0)
        or 1
    )

    return {
        "destination": destination,
        "days": days,
        "budget_inr": budget,
        "origin": origin,
        "travellers": travellers,
        "messages": [AIMessage(content="Request parsed")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ---------------------------------------------------------------------------
# Flight Agent
# ---------------------------------------------------------------------------
def flight_agent(state: TravelState):
    origin = state.get("origin", "").strip()
    destination = state.get("destination", "")
    travellers = state.get("travellers", 1)

    if not origin:
        flight_data = "NO FLIGHT DATA: departure city was not provided."
    else:
        flight_query = (
            f"Round-trip flights from {origin} to {destination} "
            f"for {travellers} traveller(s)"
        )
        try:
            flight_data = _clip(search_flights(flight_query))
        except Exception as e:
            flight_data = f"NO FLIGHT DATA: flight search failed ({e})"

    return {
        "flight_results": flight_data,
        "messages": [AIMessage(content="Flight results fetched")],
        "llm_calls": state.get("llm_calls", 0),
    }


# ---------------------------------------------------------------------------
# Hotel Agent
# ---------------------------------------------------------------------------
def hotel_agent(state: TravelState):
    destination = state.get("destination") or state["user_query"]
    query = f"Best mid-range hotels in {destination} price per night in INR 2026"
    try:
        hotel_results = _clip(_drop_stale(str(tavily_search(query))))
    except Exception as e:
        hotel_results = f"NO HOTEL DATA: hotel search failed ({e})"

    return {
        "hotel_results": hotel_results,
        "messages": [AIMessage(content="Hotel information fetched")],
        "llm_calls": state.get("llm_calls", 0),
    }


# ---------------------------------------------------------------------------
# Itinerary Agent
# ---------------------------------------------------------------------------
ITINERARY_SYSTEM = """You are an expert travel planner who is strict about facts and budgets.

Rules you must follow:
1. Use ONLY the flight and hotel data provided. Never invent airlines, fares,
   hotel names or prices. If data is missing or says NO DATA, say so clearly and
   give a clearly-labelled "estimate" instead.
2. The plan must be EXACTLY the requested number of days (Day 1 to Day N).
   No "Day 0". Arrival and departure happen within those days.
3. The grand total must NOT exceed the stated budget. Add up every line item and
   show the total. If the budget is not enough, say so and suggest what to cut.
4. Show ALL prices in INR using the rupee sign. Never use the dollar sign
   character. If a source quotes USD, convert it and write "USD" in words, and
   state the approximate exchange rate you assumed and that it must be verified.
   Hotel prices must be in INR per night.
   Entry fees: the traveller is an Indian citizen, so use the Indian-citizen
   ticket price (not the foreigner price) for Indian sites. For foreign
   destinations use the local price converted to INR.
   Flight fares with no data: give a realistic RANGE per person (not a single
   optimistic figure), label it "estimate", and base the budget on the upper end.
   Only name places that really exist, and mention weekly closing days
   (for example some Delhi monuments are closed on Mondays).
   Plan arrival and departure through the same city/airport unless you explicitly
   budget a one-way into one city and a one-way out of another.
   Do not include visa advice for domestic trips.
   Do not present a budget hotel as a 4-star; use the hotel category from the data.
5. Do not claim a pass or ticket covers something unless you are sure
   (for example, the Japan Rail Pass does not cover Nozomi/Mizuho trains).
6. Check opening hours logic (museums are not open in the evening).
7. Do NOT state calendar dates or weekdays (you do not know the travel date).
   Use Day 1, Day 2 and so on. For attractions that close on a certain weekday
   (for example Red Fort and Lotus Temple are closed on Mondays), add a note
   telling the traveller to pick their dates accordingly.
8. If flight schedule data is given, the arrival time on Day 1 must match it
   (a flight landing after midnight means no morning sightseeing that day).
   Do not invent departure times for flights that are not in the data; say the
   return flight time must be chosen when booking. Flight times from the data
   may be shown in UTC, so tell the traveller to verify local times.
9. Ignore prices from old sources. If a source says it is several years old
   (for example "18 years ago"), do not use its prices or recommendations; say
   that no current price was found and give a clearly-labelled estimate range.
10. Book one double room for two travellers, not two rooms or a single room.
    Do not claim breakfast is included unless the data says so.
    Indian-citizen entry fees at major ASI monuments are small (tens of rupees),
    not hundreds; if unsure, say "verify on the official site".
    Respect opening times (for example Red Fort opens at 09:30).
11. Be concise. Use compact tables."""


def itinerary_agent(state: TravelState):
    budget = state.get("budget_inr", 0)
    budget_text = f"INR {budget:,}" if budget else "not stated"

    prompt = f"""Create a {state.get('days', 7)}-day travel itinerary.

Original request: {state['user_query']}
Destination: {state.get('destination', '')}
Departure city: {state.get('origin') or 'not provided'}
Travellers: {state.get('travellers', 1)}
Total budget for all travellers: {budget_text}

Flight data:
{state.get('flight_results', '')}

Hotel data:
{state.get('hotel_results', '')}

Output sections:
1. Budget summary table (flights, stay, local transport, food, activities, misc, TOTAL vs budget)
2. Flights (from the data above only)
3. Hotels (from the data above only)
4. Day-by-day plan (Day 1 to Day {state.get('days', 7)})
5. Practical tips (visa, SIM, payments, weather)"""

    response = llm.invoke([
        SystemMessage(content=ITINERARY_SYSTEM),
        HumanMessage(content=prompt),
    ])

    return {
        "itinerary": response.content,
        "messages": [AIMessage(content="Itinerary drafted")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ---------------------------------------------------------------------------
# Final Response Agent: review and tidy, do not add new facts
# ---------------------------------------------------------------------------
def final_agent(state: TravelState):
    budget = state.get("budget_inr", 0)
    budget_text = f"INR {budget:,}" if budget else "not stated"

    final_prompt = f"""Review the draft travel plan below and return the final version.

Checks to perform:
- The plan covers exactly {state.get('days', 7)} days.
- The budget table adds up correctly and the total does not exceed {budget_text}.
  Fix any arithmetic mistakes.
- Remove any flight or hotel details that are not in the provided data.
- Do not add new facts. Keep it concise and well formatted.
- End with a short "Assumptions and things to verify" list.

Flight data:
{state.get('flight_results', '')}

Hotel data:
{state.get('hotel_results', '')}

Draft:
{state.get('itinerary', '')}"""

    response = llm.invoke([
        SystemMessage(content=ITINERARY_SYSTEM),
        HumanMessage(content=final_prompt),
    ])

    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------
graph = StateGraph(TravelState)

graph.add_node("parse_agent", parse_agent)
graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "parse_agent")
graph.add_edge("parse_agent", "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)


# ---------------------------------------------------------------------------
# Persistent connection so both CLI and Streamlit can share the compiled app.
# autocommit=True is required: the checkpointer migrations use
# CREATE INDEX CONCURRENTLY, which can't run inside a transaction block.
# row_factory=dict_row is required: the checkpointer reads rows by column name.
# ---------------------------------------------------------------------------
_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row,
)
checkpointer = PostgresSaver(_conn)
checkpointer.setup()

app = graph.compile(checkpointer=checkpointer)


def plan_trip(user_query: str, origin: str = "", travellers: int = 1, thread_id: str | None = None) -> str:
    """Run the full pipeline and return the final text. Handy for Streamlit too."""
    config = {
        "configurable": {
            # Fresh thread each run so old messages don't pile up.
            # Pass a fixed thread_id if you want memory across runs.
            "thread_id": thread_id or f"user_aarohi_{uuid.uuid4()}"
        }
    }

    result = app.invoke(
        {
            "messages": [HumanMessage(content=user_query)],
            "user_query": user_query,
            "origin": origin,
            "travellers": travellers,
            "flight_results": "",
            "hotel_results": "",
            "itinerary": "",
            "llm_calls": 0,
        },
        config=config,
    )
    return result["messages"][-1].content


if __name__ == "__main__":
    user_input = input("Enter travel request: ").strip()

    print("\nPlanning your trip...\n")
    answer = plan_trip(user_input)

    print("FINAL RESPONSE:\n")
    print(answer)