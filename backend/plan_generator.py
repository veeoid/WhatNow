import os
import threading
from math import atan2, cos, radians, sin, sqrt
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from pydantic import BaseModel

load_dotenv()

GEOAPIFY_BASE = "https://api.geoapify.com"


class ChatRequest(BaseModel):
    current_location: str = ""
    available_time: float = 0.0
    vibe: str = ""
    budget: float = 0.0
    transportation: str = ""
    energy_level: str = ""
    companions: str = ""
    weather: str = ""


# Every real place the tools returned during the current request, keyed by lowercased name.
# The model only ever emits place names; addresses are filled in from here so it cannot
# invent them, and any name absent from this registry is treated as hallucinated.
# The agent runs tools on worker threads, so this is module-level (a ContextVar would not
# be visible to them) and _generation_lock serializes requests to keep it per-request.
_place_registry: dict[str, dict] = {}
_generation_lock = threading.Lock()


# What the model is asked to produce. Deliberately minimal: every field it does not need to
# choose (addresses, schedule offsets, totals, map links) is computed afterwards. Asking for
# them wastes output tokens and, with map_url especially, the model fabricates long garbage
# URLs that truncate the response and fail the tool call outright.
class StopDraft(BaseModel):
    name: str
    category: str
    duration_minutes: int
    travel_minutes_to_next: int = 0
    estimated_cost: str


class PlanDraft(BaseModel):
    title: str
    summary: str
    stops: list[StopDraft]
    estimated_cost: str
    vibe_match_reason: str
    is_recommended: bool = False


class PlansDraft(BaseModel):
    plans: list[PlanDraft]


class Stop(BaseModel):
    name: str
    category: str
    address: str = ""
    start_offset_minutes: int = 0
    duration_minutes: int
    travel_minutes_to_next: int = 0
    estimated_cost: str


class Plan(BaseModel):
    title: str
    summary: str
    stops: list[Stop]
    total_duration_minutes: int = 0
    travel_time_minutes: int = 0
    estimated_cost: str
    vibe_match_reason: str
    is_recommended: bool = False
    map_url: str = ""


class PlansResponse(BaseModel):
    plans: list[Plan]


def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_m = 6_371_000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return earth_radius_m * 2 * atan2(sqrt(a), sqrt(1 - a))


@tool
def geocode_location(query: str) -> dict:
    """Look up the latitude/longitude for a free-text place or address, e.g. "Downtown Austin, TX".

    Always call this first to turn the user's current_location into coordinates
    before searching for nearby places.
    """
    try:
        response = requests.get(
            f"{GEOAPIFY_BASE}/v1/geocode/search",
            params={
                "text": query,
                "format": "json",
                "apiKey": os.environ["GEO_API_KEY"],
            },
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"error": str(exc)}

    results = response.json().get("results", [])
    if not results:
        return {"error": f"No location found for '{query}'"}
    top = results[0]
    return {"lat": top["lat"], "lon": top["lon"], "formatted": top["formatted"]}


# Rough walking/driving speeds used to turn distance into a realistic travel time.
TRANSPORT_SPEEDS_M_PER_MIN = {
    "walk": 80.0,
    "transit": 250.0,
    "drive": 500.0,
    "rideshare": 500.0,
}

# How far a user will plausibly go for one stop, by transport mode.
COMFORTABLE_DISTANCE_M = {
    "walk": 1200.0,
    "transit": 4000.0,
    "drive": 8000.0,
    "rideshare": 8000.0,
}


def travel_minutes(distance_m: float, transportation: str) -> int:
    speed = TRANSPORT_SPEEDS_M_PER_MIN.get(transportation.strip().lower(), 80.0)
    return max(1, round(distance_m / speed))


def _is_too_broad(name: str, props: dict) -> bool:
    """Reject entries that describe a whole city/region rather than somewhere you can go.

    Geoapify returns e.g. "Austin, Texas" tagged leisure.park, which is useless as a stop.
    """
    normalized = name.strip().lower()
    return normalized in {
        (props.get(field) or "").strip().lower()
        for field in ("city", "county", "state", "country", "suburb")
    }


def _score_place(place: dict, transportation: str, energy_level: str) -> float:
    """Rank a candidate 0-1 on how easy it is to actually get to and enjoy right now.

    Distance dominates: a great venue across town is a worse "right now" suggestion
    than a good one around the corner, and low energy tightens that further.
    """
    distance_m = place.get("distance_m")
    if distance_m is None:
        return 0.0

    comfortable = COMFORTABLE_DISTANCE_M.get(transportation.strip().lower(), 1200.0)
    if energy_level.strip().lower() == "low":
        comfortable *= 0.6
    elif energy_level.strip().lower() == "high":
        comfortable *= 1.5

    proximity = comfortable / (comfortable + distance_m)
    # Places with richer category tagging tend to be real destinations rather than
    # incidental map entries, so give a small nudge for it.
    detail_bonus = min(len(place.get("categories", [])), 5) / 5 * 0.15
    return round(min(proximity + detail_bonus, 1.0), 3)


@tool
def search_nearby_places(
    lat: float,
    lon: float,
    categories: str,
    transportation: str = "walk",
    energy_level: str = "medium",
    radius_m: int = 3000,
    limit: int = 20,
) -> list[dict]:
    """Search for real, currently-existing venues near a coordinate, best candidates first.

    categories: comma-separated Geoapify category codes, e.g. "catering.cafe",
    "catering.restaurant", "catering.bar", "catering.fast_food", "entertainment.museum",
    "entertainment.cinema", "entertainment.bowling_alley", "leisure.park",
    "tourism.attraction", "tourism.sights", "commercial.shopping_mall", "sport.fitness".
    Call this more than once with different categories to gather different kinds of
    stops for a plan.
    transportation / energy_level: pass the user's values so results are ranked for how
    far they can realistically travel.
    radius_m: search radius in meters (default 3000, about 2 miles).

    Results are pre-ranked and include a `score` (0-1, higher is better) and
    `travel_minutes_from_origin`. Prefer higher-scoring places; they are closer and easier
    to reach. Only use place names returned here in your final answer -- never invent a place.
    """
    try:
        response = requests.get(
            f"{GEOAPIFY_BASE}/v2/places",
            params={
                "categories": categories,
                "filter": f"circle:{lon},{lat},{radius_m}",
                "bias": f"proximity:{lon},{lat}",
                "limit": limit,
                "apiKey": os.environ["GEO_API_KEY"],
            },
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return [{"error": str(exc)}]

    places = []
    for feature in response.json().get("features", []):
        props = feature.get("properties", {})
        place_lat, place_lon = props.get("lat"), props.get("lon")
        if place_lat is None or place_lon is None:
            continue
        # Require a real venue name; unnamed entries fall back to a street address, which
        # reads as nonsense in an itinerary ("501 Colorado Street" as an ice cream stop).
        name = props.get("name")
        if not name or _is_too_broad(name, props):
            continue
        distance_m = round(_distance_meters(lat, lon, place_lat, place_lon))
        place = {
            "name": name.split(";")[0].strip(),
            "address": props.get("formatted", ""),
            "distance_m": distance_m,
            "travel_minutes_from_origin": travel_minutes(distance_m, transportation),
            "categories": props.get("categories", []),
        }
        place["score"] = _score_place(place, transportation, energy_level)
        # Geoapify joins alternate names with ";". Register each alias so a plan naming any
        # one of them still resolves instead of being discarded as invented.
        for alias in name.split(";"):
            if alias.strip():
                _place_registry.setdefault(alias.strip().lower(), place)
        places.append(place)

    if not places:
        # An empty list serializes to empty tool-message content, which the API rejects.
        return [
            {
                "note": f"No places found for categories '{categories}' within "
                f"{radius_m}m. Try different categories or a larger radius."
            }
        ]

    places.sort(key=lambda p: p["score"], reverse=True)
    # Addresses are deliberately withheld: the model only needs to choose names, and
    # generate_plans fills the real address back in from the registry.
    return [
        {
            "name": place["name"],
            "distance_m": place["distance_m"],
            "travel_minutes_from_origin": place["travel_minutes_from_origin"],
            "score": place["score"],
        }
        for place in places[:10]
    ]


SYSTEM_PROMPT = """
You are an itinerary planner for WhatNow, an app that builds real, ready-to-go plans for the
next few hours -- like a trip planner, but for right now.

You are given a numbered list of real nearby places, already ranked best-first (closest and
easiest to reach are highest). Build the itineraries entirely from that list.

Grounding rules:
- Never invent a place. Every stop's name must be copied character-for-character from the
  candidate list. Placeholder names like "Cafe No. 1" or "Local Park" are forbidden -- any
  stop whose name is not in the list is discarded.
- Prefer places nearer the top of the list; they are closer and easier to reach right now.
- Don't reuse the same place twice within one plan, and make the five plans use noticeably
  different places from each other.

Itinerary rules:
- Fill the time. Add up every stop's duration_minutes plus travel_minutes_to_next: that total
  must land between 85% and 100% of the user's available time. Never return a plan that uses
  much less -- add another stop or lengthen one instead. Never exceed it.
- travel_minutes_to_next is travel time from that stop to the following one; use 0 for the
  final stop. Base it on the travel_minutes_from_origin values you saw and the user's
  transportation mode.
- Order stops sensibly: meals at plausible mealtimes, energetic activities before winding
  down, and avoid zig-zagging back and forth across the map.
- Respect budget and transportation: don't suggest an expensive dinner on a tight budget, and
  keep travel realistic for the given mode.

Output rules:
- Produce exactly 5 distinctly different plans -- vary the mix of stops, pace, and kinds of
  places so the user has a real choice, not five versions of the same idea.
- Give each plan a short, specific, appealing title describing the actual outing (e.g.
  "Riverside coffee and a bookstore wander"), not a generic label.
- Set is_recommended to true on exactly one plan: the single best overall fit for the user's
  vibe, budget, energy, and weather. Every other plan must have is_recommended false.
- Each plan needs 2-4 real stops with realistic durations and cost estimates, and a short
  summary of the outing.
- vibe_match_reason is one positive sentence on what makes that plan appealing for this user
  -- name the specific thing that suits them. Never criticise the plan, never hedge with
  "but", and never explain why it wasn't recommended; every plan here is worth doing.
"""


llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.3)

# No tools: retrieval happens deterministically in _gather_candidates before this runs, so the
# model's only job is composing plans from a list it cannot deviate from. Letting it drive the
# searches itself proved unreliable -- it would skip a category and invent places to fill it.
agent = create_agent(
    model=llm,
    tools=[],
    system_prompt=SYSTEM_PROMPT,
    response_format=PlansDraft,
)

# Categories worth pulling for a few-hours outing, grouped so one plan can mix kinds of stops.
CANDIDATE_CATEGORIES = [
    "catering.cafe",
    "catering.restaurant",
    "catering.fast_food",
    "catering.bar,catering.pub",
    "catering.ice_cream,commercial.food_and_drink.bakery",
    "leisure.park,leisure.garden",
    "entertainment.museum,entertainment.culture.gallery",
    "entertainment.cinema,entertainment.bowling_alley,entertainment.activity_park",
    "tourism.attraction,tourism.sights",
    "commercial.shopping_mall,commercial.books",
]

MAX_CANDIDATES_PER_CATEGORY = 4


def _gather_candidates(
    lat: float, lon: float, transportation: str, energy_level: str, radius_m: int
) -> list[dict]:
    """Fetch and rank real nearby places across every category, best-first."""
    candidates: list[dict] = []
    for categories in CANDIDATE_CATEGORIES:
        results = search_nearby_places.func(
            lat=lat,
            lon=lon,
            categories=categories,
            transportation=transportation,
            energy_level=energy_level,
            radius_m=radius_m,
            limit=20,
        )
        for place in results[:MAX_CANDIDATES_PER_CATEGORY]:
            if "name" in place:
                candidates.append({**place, "category": categories.split(",")[0]})

    candidates.sort(key=lambda p: p["score"], reverse=True)
    return candidates


def _format_candidates(candidates: list[dict]) -> str:
    return "\n".join(
        f"{index}. {place['name']} | {place['category']} | "
        f"{place['travel_minutes_from_origin']} min away"
        for index, place in enumerate(candidates, start=1)
    )


def _user_message(request: ChatRequest, candidates: list[dict]) -> str:
    total_minutes = round(request.available_time * 60)
    target_low = round(total_minutes * 0.85)
    return (
        f"Nearby places you may use (ranked best first):\n"
        f"{_format_candidates(candidates)}\n\n"
        f"Current location: {request.current_location}\n"
        f"Available time: {request.available_time} hours ({total_minutes} minutes)\n"
        f"Vibe: {request.vibe}\n"
        f"Budget: ${request.budget}\n"
        f"Transportation: {request.transportation}\n"
        f"Energy level: {request.energy_level}\n"
        f"Companions: {request.companions}\n"
        f"Weather: {request.weather}\n"
        f"\n"
        f"Every plan's total_duration_minutes must be between {target_low} and "
        f"{total_minutes} minutes. A plan totalling less than {target_low} minutes is "
        f"wrong -- add stops or lengthen them until it reaches that range. Even for low "
        f"energy, fill the time with slower, restful stops rather than fewer stops.\n"
    )


MIN_STOP_MINUTES = 20
# Longest we'll credibly stretch a single stop when filling out a plan.
MAX_STOP_MINUTES = 120
TARGET_FILL = 0.85


def _fit_to_budget(plan: Plan, max_minutes: int) -> None:
    """Resize a plan's stops so it uses the user's time well without overrunning it.

    The model picks good places but is unreliable at arithmetic: it both overruns the budget
    and (especially for low energy) leaves large gaps. Enforcing the fit here rather than
    re-prompting keeps generation to one round trip and guarantees the promise the UI makes
    ("a plan for your 3 hours") actually holds.
    """
    while plan.stops:
        travel = sum(stop.travel_minutes_to_next for stop in plan.stops[:-1])
        if max_minutes - travel >= MIN_STOP_MINUTES * len(plan.stops):
            break
        plan.stops.pop()

    if not plan.stops:
        return

    travel = sum(stop.travel_minutes_to_next for stop in plan.stops[:-1])
    room_for_stops = max_minutes - travel
    planned = sum(stop.duration_minutes for stop in plan.stops)

    if planned > room_for_stops:
        scale = room_for_stops / planned
        for stop in plan.stops:
            stop.duration_minutes = max(
                MIN_STOP_MINUTES, int(stop.duration_minutes * scale)
            )
    elif planned < room_for_stops * TARGET_FILL:
        scale = room_for_stops / planned
        for stop in plan.stops:
            stop.duration_minutes = min(
                MAX_STOP_MINUTES, round(stop.duration_minutes * scale)
            )

    _trim_overflow(plan, room_for_stops)


def _trim_overflow(plan: Plan, room_for_stops: int) -> None:
    overflow = sum(stop.duration_minutes for stop in plan.stops) - room_for_stops
    while overflow > 0:
        longest = max(plan.stops, key=lambda s: s.duration_minutes)
        if longest.duration_minutes <= MIN_STOP_MINUTES:
            break
        trim = min(overflow, longest.duration_minutes - MIN_STOP_MINUTES)
        longest.duration_minutes -= trim
        overflow -= trim


def _normalize_schedule(plan: Plan) -> None:
    """Recompute the timeline from durations so the schedule is always self-consistent.

    The model reliably picks sensible durations but often gets the running offsets or the
    total slightly wrong, which would render as an itinerary that visibly doesn't add up.
    """
    offset = 0
    for index, stop in enumerate(plan.stops):
        stop.start_offset_minutes = offset
        if index == len(plan.stops) - 1:
            stop.travel_minutes_to_next = 0
        offset += stop.duration_minutes + stop.travel_minutes_to_next

    plan.total_duration_minutes = offset
    plan.travel_time_minutes = sum(stop.travel_minutes_to_next for stop in plan.stops)


def _build_plan(draft: PlanDraft, registry: dict[str, dict]) -> Plan:
    """Turn a draft into a real plan, keeping only stops that match a verified place."""
    stops = []
    seen = set()
    for draft_stop in draft.stops:
        place = registry.get(draft_stop.name.strip().lower())
        if place is None or place["name"] in seen:
            continue
        seen.add(place["name"])
        stops.append(
            Stop(
                name=place["name"],
                category=draft_stop.category,
                address=place["address"],
                duration_minutes=draft_stop.duration_minutes,
                travel_minutes_to_next=draft_stop.travel_minutes_to_next,
                estimated_cost=draft_stop.estimated_cost,
            )
        )

    return Plan(
        title=draft.title,
        summary=draft.summary,
        stops=stops,
        estimated_cost=draft.estimated_cost,
        vibe_match_reason=draft.vibe_match_reason,
        is_recommended=draft.is_recommended,
    )


def generate_plans(request: ChatRequest) -> PlansResponse:
    with _generation_lock:
        _place_registry.clear()

        origin = geocode_location.func(request.current_location)
        if "error" in origin:
            raise ValueError(
                f"Could not find '{request.current_location}': {origin['error']}"
            )

        radius_m = int(
            COMFORTABLE_DISTANCE_M.get(request.transportation.strip().lower(), 1200.0) * 2.5
        )
        candidates = _gather_candidates(
            origin["lat"],
            origin["lon"],
            request.transportation,
            request.energy_level,
            radius_m,
        )
        registry = dict(_place_registry)

        if not candidates:
            return PlansResponse(plans=[])

        result = agent.invoke(
            {
                "messages": [
                    {"role": "user", "content": _user_message(request, candidates)}
                ]
            }
        )

    draft: PlansDraft = result["structured_response"]
    response = PlansResponse(
        plans=[_build_plan(plan_draft, registry) for plan_draft in draft.plans]
    )

    max_minutes = max(MIN_STOP_MINUTES, round(request.available_time * 60))
    for plan in response.plans:
        _fit_to_budget(plan, max_minutes)
        _normalize_schedule(plan)
        if plan.stops:
            plan.map_url = (
                "https://www.google.com/maps/search/?api=1&query="
                f"{quote(plan.stops[0].address)}"
            )

    response.plans = [plan for plan in response.plans if plan.stops]

    # Exactly one recommendation, even if the model flagged zero or several.
    recommended = [plan for plan in response.plans if plan.is_recommended]
    if len(recommended) != 1 and response.plans:
        for plan in response.plans:
            plan.is_recommended = False
        (recommended[0] if recommended else response.plans[0]).is_recommended = True

    return response


if __name__ == "__main__":
    # This would be the entry point for running the script directly, if needed.
    # For example, you could create a ChatRequest object and call generate_plans(request) here.

    example_request = ChatRequest(
        current_location="Kellogg Blvd E, St. Paul, MN",
        available_time=3,
        vibe="relaxed",
        budget=50,
        transportation="walking",
        energy_level="medium",
        companions="friends",
        weather="sunny",
    )
    plans = generate_plans(example_request)
    print(plans)
