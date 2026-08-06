import os
import re
import threading
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from math import atan2, cos, radians, sin, sqrt
from typing import NamedTuple
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from groq import BadRequestError, RateLimitError
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from opening_hours import OpeningHours
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
    # The user's wall clock when they pressed Generate, e.g. "2026-08-05 15:51:23" or an
    # ISO-8601 local timestamp. Optional: without it we plan in "no clock" mode rather than
    # guessing, because the server runs in UTC and a guessed local time is worse than none.
    local_time: str = ""


# Every real place the tools returned during the current request, keyed by lowercased name.
# The model only ever emits place names; everything else about a stop -- address, category,
# kind, price, coordinates -- is looked up from here, so it cannot invent any of it.
_place_registry: dict[str, dict] = {}
_generation_lock = threading.Lock()


# What the model is asked to produce. Deliberately minimal: it names places and writes prose,
# and that is all. Every number it used to emit (durations, travel legs, costs) is now derived
# from the kind of place it picked, because asking for them both wasted output tokens and
# produced the arithmetic this module then had to correct anyway.
class PlanDraft(BaseModel):
    title: str
    summary: str
    stops: list[str]
    vibe_match_reason: str
    is_recommended: bool = False


class PlansDraft(BaseModel):
    plans: list[PlanDraft]


class Stop(BaseModel):
    name: str
    category: str = ""
    kind: str = ""
    address: str = ""
    start_offset_minutes: int = 0
    duration_minutes: int = 0
    travel_minutes_to_next: int = 0
    cost_usd: int = 0
    estimated_cost: str = ""


class Plan(BaseModel):
    title: str
    summary: str
    stops: list[Stop]
    total_duration_minutes: int = 0
    travel_time_minutes: int = 0
    estimated_cost: str = ""
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


# --- Stop kinds -------------------------------------------------------------------------
# The one semantic label a place carries through the whole pipeline. Composition limits,
# prices and durations are all read off it, so "what sort of stop is this" is decided exactly
# once, at retrieval, from Geoapify's own tagging -- never from the model.

MEAL = "meal"
QUICK_BITE = "quick_bite"
CAFE = "cafe"
TREAT = "treat"
DRINKS = "drinks"
OUTDOOR = "outdoor"
CULTURE = "culture"
ACTIVITY = "activity"
SIGHT = "sight"
SHOPPING = "shopping"

MIN_STOP_MINUTES = 15
MAX_STOP_MINUTES = 120


class KindSpec(NamedTuple):
    label: str  # how the kind is described to the model in the candidate list
    phrase: str  # used by the prose fallbacks, e.g. "then coffee"
    min_minutes: int
    typical_minutes: int
    max_minutes: int
    cost_usd: int  # per person, mid-market, 2026 US
    open_from: float  # earliest hour you'd plausibly be there
    open_to: float  # latest hour you'd plausibly be there


# Every duration bound is a multiple of 5 so that rounding a stop to the nearest 5 minutes can
# never push it outside its own band.
KIND_SPECS: dict[str, KindSpec] = {
    MEAL: KindSpec("sit-down meal", "a sit-down meal", 45, 75, 105, 25, 11.0, 21.5),
    QUICK_BITE: KindSpec("quick bite", "a quick bite", 20, 30, 45, 12, 8.0, 22.0),
    CAFE: KindSpec("cafe", "coffee", 25, 40, 60, 6, 7.0, 19.0),
    TREAT: KindSpec("dessert", "something sweet", 15, 25, 35, 7, 10.0, 22.0),
    DRINKS: KindSpec("drinks", "a drink", 45, 60, 90, 14, 15.0, 24.0),
    OUTDOOR: KindSpec("park", "time outside", 30, 50, 90, 0, 6.0, 20.5),
    CULTURE: KindSpec("museum", "a museum stop", 45, 70, 120, 12, 10.0, 17.0),
    ACTIVITY: KindSpec("activity", "something to do", 60, 90, 120, 18, 10.0, 23.0),
    SIGHT: KindSpec("landmark", "a landmark", 15, 25, 35, 0, 6.0, 22.0),
    SHOPPING: KindSpec("shops", "a browse round the shops", 30, 45, 75, 0, 10.0, 20.0),
}

FALLBACK_SPEC = KindSpec(
    "stop", "a stop", MIN_STOP_MINUTES, 45, MAX_STOP_MINUTES, 0, 6.0, 23.0
)

SHORTEST_STOP_MINUTES = min(spec.min_minutes for spec in KIND_SPECS.values())

# Geoapify category prefix -> kind, in priority order: the first prefix a place matches wins.
# Non-consumption comes first so a museum with a cafe inside stays a museum. Within food and
# drink, the cheaper/shorter kinds come first so a cafe that also tags itself a restaurant is
# priced and timed as coffee rather than as dinner.
CATEGORY_KINDS: tuple[tuple[str, str], ...] = (
    ("entertainment.museum", CULTURE),
    ("entertainment.culture", CULTURE),
    ("entertainment.cinema", ACTIVITY),
    ("entertainment.bowling_alley", ACTIVITY),
    ("entertainment.activity_park", ACTIVITY),
    ("entertainment.escape_game", ACTIVITY),
    ("sport", ACTIVITY),
    ("leisure.park", OUTDOOR),
    ("leisure.garden", OUTDOOR),
    ("natural", OUTDOOR),
    ("commercial.shopping_mall", SHOPPING),
    ("commercial.books", SHOPPING),
    ("catering.ice_cream", TREAT),
    ("commercial.food_and_drink.bakery", TREAT),
    ("catering.cafe", CAFE),
    ("catering.fast_food", QUICK_BITE),
    ("catering.food_court", QUICK_BITE),
    ("catering.bar", DRINKS),
    ("catering.pub", DRINKS),
    ("catering.biergarten", DRINKS),
    ("catering.restaurant", MEAL),
    # Below catering on purpose. Plenty of landmarks are also somewhere you eat -- Mickey's
    # Diner is a listed historic building -- and calling one a free 25-minute sight when the
    # user will sit down and order is exactly the fiction this table exists to prevent.
    ("tourism.attraction", SIGHT),
    ("tourism.sights", SIGHT),
    ("commercial", SHOPPING),
    ("catering", QUICK_BITE),
    ("entertainment", ACTIVITY),
    ("leisure", OUTDOOR),
    ("tourism", SIGHT),
)

# The handful of places where a flat per-kind price is plainly wrong.
CATEGORY_COST_OVERRIDES: dict[str, int] = {
    "entertainment.culture.gallery": 0,  # you can walk into a gallery for nothing
    "commercial.books": 0,
    "entertainment.cinema": 16,
    "entertainment.bowling_alley": 22,
}

# OpenStreetMap's `cuisine` tag, which Geoapify passes through untouched in datasource.raw and
# which is populated on ~60% of the eating and drinking places we retrieve. It is the only
# price signal available for free: OSM's actual `price_range` tag is present on 0% of them, and
# every commercial source that carries a real price band (Google priceLevel, Yelp $/$$/$$$)
# is metered and forbids caching. A multiplier on the kind's base cost is all this can support
# -- it separates the burger counter from the bistro, not one bistro from another.
CUISINE_MULTIPLIERS: dict[str, float] = {
    # counter service and grab-and-go
    "sandwich": 0.6, "burger": 0.6, "pizza": 0.7, "chicken": 0.6, "bagel": 0.5,
    "donut": 0.5, "salad": 0.6, "juice": 0.5, "bubble_tea": 0.5, "poke": 0.8,
    "ice_cream": 0.5, "coffee_shop": 0.7, "tea": 0.6, "hot_dog": 0.5, "taco": 0.6,
    "kebab": 0.6, "fish_and_chips": 0.7, "wrap": 0.6, "deli": 0.7, "bakery": 0.6,
    "smoothie": 0.5, "cafeteria": 0.6, "food_court": 0.6, "noodle": 0.8, "ramen": 0.9,
    "pretzel": 0.5, "crepe": 0.7, "waffle": 0.6, "burrito": 0.6, "sub": 0.6,
    # sit-down, mid-market: left at 1.0 by omission (american, mexican, italian, thai,
    # chinese, vietnamese, mediterranean, indian, pub, barbecue, brunch, greek, korean...)
    # white tablecloth
    "french": 1.6, "seafood": 1.5, "sushi": 1.5, "japanese": 1.3, "spanish": 1.3,
    "tapas": 1.3, "steak_house": 1.9, "oyster": 1.7, "fine_dining": 2.4,
    "molecular": 2.4, "wine_bar": 1.4, "cocktail": 1.3,
}

# A chain is a known quantity and priced to be one, whatever its cuisine says.
CHAIN_MULTIPLIER = 0.8

# Nothing you consume is free, however cheap the signal says it is.
MIN_CONSUMPTION_COST = 3

CONSUMPTION_KINDS = frozenset({MEAL, QUICK_BITE, CAFE, TREAT, DRINKS})

# Kinds that compete for the same slot in an outing: you eat once.
KIND_SLOTS = {MEAL: "eat", QUICK_BITE: "eat"}

# An outing, not a food crawl. With three or more stops this also guarantees at least one
# stop that isn't eating or drinking, so that doesn't need to be a separate rule.
MAX_CONSUMPTION_STOPS = 2

# Past this, let the plan be short and let the top-up pass fill it. Substituting without a cap
# makes all five plans converge on whatever the single best unused candidate is, which trades a
# composition bug for a worse one: five cards that offer no choice.
MAX_SUBSTITUTIONS = 2

MEAL_WINDOWS = {
    "breakfast": (7.0, 10.5),
    "brunch": (10.0, 13.0),
    "lunch": (11.5, 14.0),
    "dinner": (17.0, 21.0),
}

WET_WEATHER_WORDS = ("rain", "drizzle", "snow", "thunder", "sleet", "shower", "storm")


def _matches(code: str, prefix: str) -> bool:
    return code == prefix or code.startswith(prefix + ".")


def _classify(categories: list[str], requested: str = "") -> tuple[str, str]:
    """Return (kind, category) for a place from its Geoapify category codes.

    Geoapify tags one venue with a whole tree -- "catering", "catering.restaurant",
    "catering.restaurant.pizza" -- and mixed venues carry two branches at once, so the priority
    order of CATEGORY_KINDS, not the order Geoapify happened to list them in, is what decides
    what the place counts as in a plan.
    """
    codes = [code for code in categories if code]
    for prefix, kind in CATEGORY_KINDS:
        matched = [code for code in codes if _matches(code, prefix)]
        if not matched:
            continue
        # Keep one level of detail below the prefix so the UI can label the stop "Gallery" or
        # "Bakery" rather than "Culture", but no deeper: the leaves get very odd.
        depth = prefix.count(".") + 2
        category = min(
            (".".join(code.split(".")[:depth]) for code in matched),
            key=lambda code: (-code.count("."), code),
        )
        return kind, category

    # Nothing recognisable: fall back to the group we asked Geoapify for.
    for prefix, kind in CATEGORY_KINDS:
        if requested and any(_matches(part, prefix) for part in requested.split(",")):
            return kind, requested.split(",")[0]
    return SIGHT, codes[0] if codes else ""


def _price_multiplier(raw: dict) -> float:
    """How far this venue sits from the middle of its kind, read off its OSM tags."""
    cuisines = [c.strip().lower() for c in str(raw.get("cuisine") or "").split(";") if c.strip()]
    # Take the dearest of several tags rather than the cheapest: "pizza;italian" is a
    # restaurant that happens to serve pizza, and underestimating is the failure that put
    # $8 dinners on the cards in the first place.
    multiplier = max((CUISINE_MULTIPLIERS.get(c, 1.0) for c in cuisines), default=1.0)
    if raw.get("brand") or raw.get("brand:wikidata"):
        multiplier = min(multiplier, CHAIN_MULTIPLIER)
    return multiplier


def _cost_for(kind: str, category: str, raw: dict | None = None) -> int:
    for prefix, dollars in CATEGORY_COST_OVERRIDES.items():
        if _matches(category, prefix):
            return dollars

    base = KIND_SPECS.get(kind, FALLBACK_SPEC).cost_usd
    if not base or kind not in CONSUMPTION_KINDS:
        return base
    return max(MIN_CONSUMPTION_COST, round(base * _price_multiplier(raw or {})))


def _spec(stop: Stop) -> KindSpec:
    return KIND_SPECS.get(stop.kind, FALLBACK_SPEC)


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
    transportation / energy_level: the user's values, so results are ranked for how far they
    can realistically travel.
    radius_m: search radius in meters (default 3000, about 2 miles).

    Results are pre-ranked and carry a `score` (0-1, higher is better), a semantic `kind`, a
    per-person `cost_usd` and coordinates.
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
        kind, category = _classify(props.get("categories", []), categories)
        # Geoapify passes OpenStreetMap's own tags through here at no extra cost or call.
        raw = (props.get("datasource") or {}).get("raw") or {}
        place = {
            "name": name.split(";")[0].strip(),
            "address": props.get("formatted", ""),
            "lat": place_lat,
            "lon": place_lon,
            "distance_m": distance_m,
            "travel_minutes_from_origin": travel_minutes(distance_m, transportation),
            "categories": props.get("categories", []),
            "kind": kind,
            "category": category,
            "cost_usd": _cost_for(kind, category, raw),
            "opening_hours": str(raw.get("opening_hours") or ""),
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
    return places[:10]


SYSTEM_PROMPT = """
You are an itinerary planner for WhatNow, an app that builds real, ready-to-go plans for the
next few hours -- like a trip planner, but for right now.

You are given a numbered list of real nearby places, already ranked best-first. Each line shows
what kind of stop it is, how far away it is, how long a stop there normally takes, and what it
normally costs one person. Build the itineraries entirely from that list.

Grounding rules:
- Never invent a place. Every stop name must be copied character-for-character from the
  candidate list. Placeholder names like "Cafe No. 1" or "Local Park" are forbidden -- any stop
  whose name is not in the list is discarded.
- Prefer places nearer the top of the list; they are closer and easier to reach right now.
- Don't reuse a place within a plan, and make the five plans use noticeably different places.

Composition rules -- this is an outing, not a food crawl:
- Never put two stops of the same kind in one plan: no two restaurants, no two cafes, no two
  bars, no two parks, no two museums. Nobody eats two dinners or drinks coffee twice in a row.
- One eating stop at most (a sit-down meal or a quick bite, never both), one cafe at most, one
  dessert stop at most, one drinks stop at most.
- At most two eating-or-drinking stops in a plan. Any plan of three or more stops must include
  something that isn't consumption: a park, a museum, a landmark, shops, an activity.
- Alternate doing and sitting. Never put two tables in a row.

Budget rules:
- The price on each line is what one person really spends there. Add up the stops you choose;
  the total must stay inside the user's budget.
- Never pick a stop you can't afford on the assumption it will come out cheaper than the price
  shown. If a sit-down meal doesn't fit the budget, the plan gets coffee, a quick bite or free
  stops instead -- a cheap plan is a good plan, an unaffordable one is a broken plan.

Timing rules:
- Only call a stop breakfast, brunch, lunch or dinner if that mealtime actually falls inside
  the window given below.
- Only pick places plausibly open then: museums and shops close in the early evening, bars
  aren't an afternoon stop, parks are for daylight.
- A line marked CLOSES tells you when that place actually shuts. Put it early enough in the
  plan that the user gets there well before then -- a stop reached after closing is thrown
  away and replaced, and the plan you wrote about stops being the plan they get.
- Match the weather you are given. In rain or snow, build the plan around indoor stops and
  don't promise a walk, a view or a stroll: outdoor stops are dropped from wet-weather plans
  automatically, so a plan written around one loses it and the title stops making sense.
- Order stops sensibly: eat at mealtimes, energetic things before winding down, and don't
  zig-zag back and forth across the map.

Output rules:
- Produce exactly 5 distinctly different plans -- vary the mix of kinds, the pace and the part
  of town, so the user gets a real choice rather than five versions of one idea.
- Use exactly the number of stops asked for below, listed in the order they would happen.
- Title: short, specific, about this outing -- name something you would actually see or do
  ("Riverside coffee and a bookstore wander", "Sunset on the bluff, then tacos"). Category
  labels are forbidden: never "Food and Drink", "Culture", "Outdoor Fun", "Shopping Trip".
- Summary: one or two sentences on what the outing feels like and who it suits -- its shape,
  not its contents. Never name the stops; the timeline underneath already lists them.
  Bad: "A visit to X for lunch, followed by a stop at Y and ending with a drink at Z."
  Good: "An unhurried loop by the water with one long sit-down in the middle."
- vibe_match_reason is one positive sentence on what makes that plan appealing for this user
  -- name the specific thing that suits them. Never criticise the plan, never hedge with
  "but", and never explain why it wasn't recommended; every plan here is worth doing.
- Set is_recommended to true on exactly one plan: the single best overall fit for the user's
  vibe, budget, energy and weather. Every other plan must have is_recommended false.
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

# Half the category groups above are food and drink, so an unbalanced pool is what quietly
# instructs the model to build food crawls in dense downtowns. Cap the consumption kinds harder
# than the rest and interleave, so the top of the list is a mix rather than ten restaurants.
MAX_CANDIDATES_PER_CONSUMPTION_KIND = 3
MAX_CANDIDATES_PER_KIND = 4
MAX_CANDIDATES = 30


def _interleave_by_kind(candidates: list[dict], limit: int = MAX_CANDIDATES) -> list[dict]:
    """Round-robin the best of each kind so the top of the list isn't all restaurants.

    The model is told to prefer places near the top, so ordering purely by distance is an
    instruction it faithfully follows into a three-restaurant plan.
    """
    buckets: dict[str, list[dict]] = {}
    for place in candidates:
        buckets.setdefault(place["kind"], []).append(place)

    ordered: list[dict] = []
    while buckets and len(ordered) < limit:
        for kind in list(buckets):
            ordered.append(buckets[kind].pop(0))
            if not buckets[kind]:
                del buckets[kind]
            if len(ordered) >= limit:
                break
    return ordered


def _gather_candidates(
    lat: float, lon: float, transportation: str, energy_level: str, radius_m: int
) -> list[dict]:
    """Fetch, rank and balance real nearby places across every kind of stop."""
    by_name: dict[str, dict] = {}
    per_kind: dict[str, int] = {}

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
        for place in results:
            if "name" not in place:
                continue
            key = place["name"].strip().lower()
            # A gastropub comes back from both the bar group and the restaurant group.
            if key in by_name:
                continue
            kind = place["kind"]
            cap = (
                MAX_CANDIDATES_PER_CONSUMPTION_KIND
                if kind in CONSUMPTION_KINDS
                else MAX_CANDIDATES_PER_KIND
            )
            if per_kind.get(kind, 0) >= cap:
                continue
            by_name[key] = place
            per_kind[kind] = per_kind.get(kind, 0) + 1

    candidates = sorted(by_name.values(), key=lambda p: p["score"], reverse=True)
    return _interleave_by_kind(candidates)


# --- Time of day ------------------------------------------------------------------------


def _parse_local_time(raw: str) -> datetime | None:
    """The user's wall clock, or None when we genuinely don't know what time it is.

    Never fall back to the server clock: the backend runs in UTC, so a guessed local time is
    not a safe default -- it is the "lunch at 3:51 PM" bug with more confidence behind it.
    """
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    # We want the clock face the user is looking at, not an instant on a timeline.
    parsed = parsed.replace(tzinfo=None)
    if abs(parsed - datetime.now(timezone.utc).replace(tzinfo=None)) > timedelta(days=2):
        return None
    return parsed


def _plan_window(request: ChatRequest) -> tuple[datetime, datetime] | None:
    start = _parse_local_time(request.local_time)
    if start is None:
        return None
    return start, start + timedelta(hours=max(request.available_time, 0.5))


def _window_hours(window: tuple[datetime, datetime]) -> tuple[float, float]:
    start, end = window
    start_h = start.hour + start.minute / 60
    return start_h, min(start_h + (end - start).total_seconds() / 3600, 24.0)


def _kind_open_in_window(kind: str, window: tuple[datetime, datetime] | None) -> bool:
    if window is None:
        return True
    spec = KIND_SPECS.get(kind, FALLBACK_SPEC)
    start_h, end_h = _window_hours(window)
    return spec.open_from < end_h and spec.open_to > start_h


def _meals_in_window(window: tuple[datetime, datetime]) -> list[str]:
    start_h, end_h = _window_hours(window)
    return [
        meal
        for meal, (from_h, to_h) in MEAL_WINDOWS.items()
        if from_h < end_h and to_h > start_h
    ]


def _clock(moment: datetime) -> str:
    return moment.strftime("%I:%M %p").lstrip("0")


# --- Real opening hours -------------------------------------------------------------------
# OpenStreetMap's opening_hours tag, passed through by Geoapify at no extra cost, present on
# roughly half the venues we retrieve. It replaces the KIND_SPECS stereotype ("museums shut at
# five") with the fact, for the half of places that state it. Parsing is delegated: half these
# values carry several rules, one in nine runs past midnight, and a few carry seasonal dates
# and public-holiday exceptions -- a regex would be wrong often, and wrong in the direction of
# sending someone to a locked door.


@lru_cache(maxsize=2048)
def _hours(text: str) -> OpeningHours | None:
    if not text:
        return None
    try:
        return OpeningHours(text)
    except Exception:  # noqa: BLE001 - malformed OSM hours must degrade to "unknown", not 500
        return None


def _open_at(text: str, moment: datetime) -> bool | None:
    """True/False when the venue states its hours, None when we simply don't know."""
    parsed = _hours(text)
    if parsed is None:
        return None
    try:
        return bool(parsed.is_open(moment))
    except Exception:  # noqa: BLE001 - malformed OSM hours must degrade to "unknown", not 500
        return None


def _open_during_window(text: str, window: tuple[datetime, datetime] | None) -> bool:
    """Is the venue open at any point in the outing? Unknown hours are given the benefit."""
    parsed = _hours(text)
    if parsed is None or window is None:
        return True
    start, end = window
    try:
        if parsed.is_open(start):
            return True
        opens = parsed.next_change(start)
    except Exception:  # noqa: BLE001 - malformed OSM hours must degrade to "unknown", not 500
        return True
    return opens is not None and opens < end


def _closes_at(
    text: str, window: tuple[datetime, datetime] | None
) -> datetime | None:
    """When the venue shuts, if that happens before the outing ends. Worth telling the model:
    it's what makes it put the museum first rather than last."""
    parsed = _hours(text)
    if parsed is None or window is None:
        return None
    start, end = window
    try:
        if not parsed.is_open(start):
            return None
        change = parsed.next_change(start)
    except Exception:  # noqa: BLE001 - malformed OSM hours must degrade to "unknown", not 500
        return None
    return change if change is not None and change < end else None


def _stop_is_open_on_arrival(
    stop: Stop, registry: dict[str, dict], window: tuple[datetime, datetime]
) -> bool:
    """Would you actually get in, and get a worthwhile stay out of it?

    Checking the door is open on arrival isn't enough -- arriving at a museum twenty minutes
    before it locks up is a stop the user cannot use, so it also has to still be open for the
    shortest visit that kind justifies.
    """
    place = registry.get(stop.name.strip().lower())
    if not place:
        return True
    hours = place.get("opening_hours", "")
    arrival = window[0] + timedelta(minutes=stop.start_offset_minutes)
    stay = min(stop.duration_minutes, _spec(stop).min_minutes)
    return (
        _open_at(hours, arrival) is not False
        and _open_at(hours, arrival + timedelta(minutes=stay)) is not False
    )


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


# --- Composition ------------------------------------------------------------------------


def _bad_weather(weather: str) -> bool:
    lowered = weather.lower()
    return any(word in lowered for word in WET_WEATHER_WORDS)


def _plan_state(plan: Plan) -> tuple[set[str], set[str], int, int]:
    names = {stop.name for stop in plan.stops}
    kinds = {stop.kind for stop in plan.stops}
    consumption = sum(1 for stop in plan.stops if stop.kind in CONSUMPTION_KINDS)
    spent = sum(stop.cost_usd for stop in plan.stops)
    return names, kinds, consumption, spent


def _stop_is_allowed(
    kind: str,
    cost_usd: int,
    kinds: set[str],
    consumption: int,
    spent: int,
    budget: float,
    request: ChatRequest,
    window: tuple[datetime, datetime] | None,
) -> bool:
    """The whole composition rulebook, applied to one candidate stop."""
    if kind in kinds:
        return False
    slot = KIND_SLOTS.get(kind)
    if slot and any(KIND_SLOTS.get(other) == slot for other in kinds):
        return False
    if kind in CONSUMPTION_KINDS and consumption >= MAX_CONSUMPTION_STOPS:
        return False
    # This is what turns a $15 budget into a park-and-coffee plan instead of three restaurants
    # with invented $8 prices: a sit-down meal simply isn't an option at that budget.
    if spent + cost_usd > budget:
        return False
    if not _kind_open_in_window(kind, window):
        return False
    if kind == DRINKS and request.companions.strip().lower() == "family":
        return False
    return not (kind == OUTDOOR and _bad_weather(request.weather))


def _stop_from_place(place: dict) -> Stop:
    spec = KIND_SPECS.get(place["kind"], FALLBACK_SPEC)
    return Stop(
        name=place["name"],
        category=place["category"],
        kind=place["kind"],
        address=place["address"],
        duration_minutes=spec.typical_minutes,
        cost_usd=place["cost_usd"],
    )


def _max_detour_minutes(transportation: str) -> int:
    """How far out of the way an optional extra stop may drag the route."""
    mode = transportation.strip().lower()
    return round(
        COMFORTABLE_DISTANCE_M.get(mode, 1200.0)
        / TRANSPORT_SPEEDS_M_PER_MIN.get(mode, 80.0)
    )


def _leg_minutes(here: dict, there: dict, transportation: str) -> int:
    return travel_minutes(
        _distance_meters(here["lat"], here["lon"], there["lat"], there["lon"]),
        transportation,
    )


def _detour_minutes(
    place: dict,
    before: Stop | None,
    after: Stop | None,
    registry: dict[str, dict],
    transportation: str,
) -> int:
    """Extra travel that dropping this place between two stops would cost.

    `score` measures distance from where the user is standing now, which is the right way to
    rank the first stop and the wrong way to rank every stop after it: two places can each be
    five minutes from the origin and twenty minutes from each other. Ranking substitutions and
    additions by score is what put 52 minutes of walking into a three-hour "chill" outing.
    """
    start = registry.get(before.name.strip().lower()) if before else None
    end = registry.get(after.name.strip().lower()) if after else None

    incoming = (
        _leg_minutes(start, place, transportation)
        if start
        else place["travel_minutes_from_origin"]
    )
    outgoing = _leg_minutes(place, end, transportation) if end else 0
    if start and end:
        skipped = _leg_minutes(start, end, transportation)
    elif end:
        skipped = end["travel_minutes_from_origin"]
    else:
        skipped = 0
    return max(0, incoming + outgoing - skipped)


def _pick_candidate(
    plan: Plan,
    pool: list[dict],
    request: ChatRequest,
    window: tuple[datetime, datetime] | None,
    budget: float,
    used_globally: set[str],
    registry: dict[str, dict],
    at_moment: datetime | None = None,
    before: Stop | None = None,
    after: Stop | None = None,
    max_detour: int | None = None,
) -> Stop | None:
    """Best unused candidate that this plan is still allowed to take.

    Places already spent on an earlier plan sort last rather than being excluded: the point is
    that the five cards diverge, not that a genuinely good nearby park appears only once.

    Ranking is by detour first, rounded to five minutes so that anything comparably close is
    still separated by `score` -- the richer-tagged place tends to be the real destination.
    """
    names, kinds, consumption, spent = _plan_state(plan)
    if before is None and after is None and plan.stops:
        before = plan.stops[-1]

    detours = {
        place["name"]: _detour_minutes(
            place, before, after, registry, request.transportation
        )
        for place in pool
    }
    ordered = sorted(
        pool,
        key=lambda p: (
            p["name"] in used_globally,
            round(detours[p["name"]] / 5),
            -p["score"],
        ),
    )
    for place in ordered:
        if max_detour is not None and detours[place["name"]] > max_detour:
            continue
        if place["name"] in names:
            continue
        if at_moment is not None and _open_at(
            place.get("opening_hours", ""), at_moment
        ) is False:
            continue
        if not _stop_is_allowed(
            place["kind"],
            place["cost_usd"],
            kinds,
            consumption,
            spent,
            budget,
            request,
            window,
        ):
            continue
        return _stop_from_place(place)
    return None


def _enforce_composition(
    plan: Plan,
    pool: list[dict],
    registry: dict[str, dict],
    request: ChatRequest,
    window: tuple[datetime, datetime] | None,
    budget: float,
    used_globally: set[str],
) -> None:
    """Replace stops that break the composition rules with the best allowed candidate.

    Substituting rather than dropping keeps the plan's shape: drop a stop and the fit stretches
    whatever survives across the whole window, which is how you get a three-hour coffee. This
    is also why the prompt forbids the summary from naming stops -- a substituted stop must not
    be able to contradict the prose written before it existed.
    """
    original = plan.stops
    plan.stops = []
    substitutions = 0

    for stop in original:
        names, kinds, consumption, spent = _plan_state(plan)
        if stop.name not in names and _stop_is_allowed(
            stop.kind,
            stop.cost_usd,
            kinds,
            consumption,
            spent,
            budget,
            request,
            window,
        ):
            plan.stops.append(stop)
            continue
        if substitutions >= MAX_SUBSTITUTIONS:
            continue
        # The replacement lands where the rejected stop was, so it is ranked against the stop
        # it will follow rather than against the origin.
        replacement = _pick_candidate(
            plan, pool, request, window, budget, used_globally, registry
        )
        if replacement is None:
            continue
        substitutions += 1
        plan.stops.append(replacement)


# --- Travel, duration and schedule -------------------------------------------------------


def _diversify(
    plan: Plan,
    seen: set[frozenset[str]],
    pool: list[dict],
    registry: dict[str, dict],
    request: ChatRequest,
    window: tuple[datetime, datetime] | None,
    budget: float,
    used_globally: set[str],
) -> bool:
    """Keep this plan from being a repeat of one already built. False means give up on it.

    Composition only substitutes on a rule violation, and two drafts naming the same place
    break no rule -- which is how a thin candidate pool (free stops only, rain ruling out the
    parks) ends with the same single landmark on two cards.
    """
    if frozenset(stop.name for stop in plan.stops) not in seen:
        return True

    dropped = plan.stops.pop()
    replacement = _pick_candidate(
        plan, pool, request, window, budget, used_globally, registry
    )
    plan.stops.append(replacement if replacement is not None else dropped)
    return frozenset(stop.name for stop in plan.stops) not in seen


def _origin_travel(plan: Plan, registry: dict[str, dict]) -> int:
    if not plan.stops:
        return 0
    place = registry.get(plan.stops[0].name.strip().lower())
    return place["travel_minutes_from_origin"] if place else 0


def _travel_total(plan: Plan, registry: dict[str, dict]) -> int:
    return _origin_travel(plan, registry) + sum(
        stop.travel_minutes_to_next for stop in plan.stops[:-1]
    )


def _recompute_travel(
    plan: Plan, registry: dict[str, dict], transportation: str
) -> None:
    """Derive each leg from the two places' own coordinates.

    The model used to infer a leg from two distances-from-origin, which says nothing about the
    distance between the stops themselves, and it is also what made substitution unsafe: swap a
    stop and the inherited travel number describes a journey nobody is taking.
    """
    for index, stop in enumerate(plan.stops):
        if index == len(plan.stops) - 1:
            stop.travel_minutes_to_next = 0
            continue
        here = registry.get(stop.name.strip().lower())
        nxt = registry.get(plan.stops[index + 1].name.strip().lower())
        if not here or not nxt:
            continue
        stop.travel_minutes_to_next = travel_minutes(
            _distance_meters(here["lat"], here["lon"], nxt["lat"], nxt["lon"]),
            transportation,
        )


def _target_stop_count(request: ChatRequest) -> int:
    """How many stops the window justifies. Python owns this because it also owns durations.

    The model can no longer pad a short plan out with invented durations, so if it were left to
    choose the count, a four-hour window would come back as two stops stretched to breaking.
    """
    count = min(4, max(2, round(max(request.available_time, 1.0))))
    # Low energy means a slower outing, not a solitary stop: never cut below two, or a
    # two-hour window comes back as one place stretched across the whole afternoon.
    if request.energy_level.strip().lower() == "low" and count > 2:
        count -= 1
    return count


def _drop_until_fits(plan: Plan, max_minutes: int, registry: dict[str, dict]) -> None:
    while plan.stops:
        travel = _travel_total(plan, registry)
        needed = sum(_spec(stop).min_minutes for stop in plan.stops)
        if max_minutes - travel >= needed:
            break
        plan.stops.pop()
        if plan.stops:
            plan.stops[-1].travel_minutes_to_next = 0


def _top_up(
    plan: Plan,
    max_minutes: int,
    pool: list[dict],
    registry: dict[str, dict],
    request: ChatRequest,
    window: tuple[datetime, datetime] | None,
    budget: float,
    used_globally: set[str],
) -> None:
    """Add a stop rather than stretch one. A four-hour window is an outing, not a long lunch.

    Unlike a substitution, this stop is optional -- so it is also capped on detour. Two stops
    close together beat three with a fifteen-minute trudge between them, especially for the
    user who asked for chill.
    """
    while len(plan.stops) < _target_stop_count(request):
        candidate = _pick_candidate(
            plan,
            pool,
            request,
            window,
            budget,
            used_globally,
            registry,
            max_detour=_max_detour_minutes(request.transportation),
        )
        if candidate is None:
            return
        plan.stops.append(candidate)
        _recompute_travel(plan, registry, request.transportation)
        needed = sum(_spec(stop).min_minutes for stop in plan.stops)
        if max_minutes - _travel_total(plan, registry) < needed:
            plan.stops.pop()
            _recompute_travel(plan, registry, request.transportation)
            return


def _stretch(spec: KindSpec, bound_minutes: int, factor: float) -> float:
    return spec.typical_minutes + factor * (bound_minutes - spec.typical_minutes)


def _assign_durations(plan: Plan, max_minutes: int, registry: dict[str, dict]) -> None:
    """Start every stop at what that kind normally takes, then move them all in proportion.

    One shared stretch factor across the plan means each stop flexes by its own slack: a museum
    absorbs an extra half hour, a bakery doesn't, and nothing lands on "1h 18m" because the
    result is snapped to five minutes at the end.
    """
    if not plan.stops:
        return

    room = max_minutes - _travel_total(plan, registry)
    specs = [_spec(stop) for stop in plan.stops]
    typical = sum(spec.typical_minutes for spec in specs)
    grow = typical < room
    bounds = [spec.max_minutes if grow else spec.min_minutes for spec in specs]

    low, high = 0.0, 1.0
    for _ in range(24):
        mid = (low + high) / 2
        total = sum(
            _stretch(spec, bound, mid) for spec, bound in zip(specs, bounds)
        )
        if (total < room) if grow else (total > room):
            low = mid
        else:
            high = mid
    factor = low if grow else high

    for stop, spec, bound in zip(plan.stops, specs, bounds):
        minutes = _stretch(spec, bound, factor)
        stop.duration_minutes = min(
            spec.max_minutes, max(spec.min_minutes, 5 * round(minutes / 5))
        )

    _trim_overflow(plan, room)


def _trim_overflow(plan: Plan, room: int) -> None:
    overflow = sum(stop.duration_minutes for stop in plan.stops) - room
    while overflow > 0:
        loosest = max(plan.stops, key=lambda s: s.duration_minutes - _spec(s).min_minutes)
        slack = loosest.duration_minutes - _spec(loosest).min_minutes
        if slack <= 0:
            return
        step = min(slack, 5 * max(1, overflow // 5))
        loosest.duration_minutes -= step
        overflow -= step


def _fit_to_time(
    plan: Plan,
    max_minutes: int,
    pool: list[dict],
    registry: dict[str, dict],
    request: ChatRequest,
    window: tuple[datetime, datetime] | None,
    budget: float,
    used_globally: set[str],
) -> None:
    """Make the plan use the user's time well without overrunning it."""
    _drop_until_fits(plan, max_minutes, registry)
    _top_up(plan, max_minutes, pool, registry, request, window, budget, used_globally)
    _assign_durations(plan, max_minutes, registry)


def _stop_detour(
    plan: Plan, index: int, registry: dict[str, dict], transportation: str
) -> int:
    """Extra travel this stop costs versus skipping it and going straight on."""
    place = registry.get(plan.stops[index].name.strip().lower())
    if not place:
        return 0
    return _detour_minutes(
        place,
        plan.stops[index - 1] if index else None,
        plan.stops[index + 1] if index + 1 < len(plan.stops) else None,
        registry,
        transportation,
    )


def _relocate_outliers(
    plan: Plan,
    registry: dict[str, dict],
    pool: list[dict],
    request: ChatRequest,
    window: tuple[datetime, datetime] | None,
    budget: float,
    used_globally: set[str],
    max_minutes: int,
) -> None:
    """Swap out the one place dragging the route, keeping the plan's order and shape.

    Ranking substitutions by detour fixes the stops this module chooses, but not the ones the
    model chose: it only ever sees how far each candidate is from the user, never how far they
    are from each other, so three individually-close places can still zig-zag. Reordering them
    would read worse than the walk does -- nobody wants the nightcap before dinner -- so the
    outlier is relocated instead. Each pass must strictly beat the detour it replaces, so this
    terminates.
    """
    for _ in range(len(plan.stops)):
        cap = _max_detour_minutes(request.transportation)
        worst_index = None
        for index in range(len(plan.stops)):
            detour = _stop_detour(plan, index, registry, request.transportation)
            if detour > cap:
                worst_index, cap = index, detour
        if worst_index is None:
            return

        stranded = plan.stops[worst_index]
        before = plan.stops[worst_index - 1] if worst_index else None
        after = (
            plan.stops[worst_index + 1]
            if worst_index + 1 < len(plan.stops)
            else None
        )
        plan.stops.pop(worst_index)
        replacement = _pick_candidate(
            plan,
            pool,
            request,
            window,
            budget,
            used_globally,
            registry,
            before=before,
            after=after,
            max_detour=cap - 1,
        )
        plan.stops.insert(worst_index, replacement or stranded)
        if replacement is None:
            return
        _recompute_travel(plan, registry, request.transportation)
        _assign_durations(plan, max_minutes, registry)


def _enforce_opening_hours(
    plan: Plan,
    registry: dict[str, dict],
    pool: list[dict],
    request: ChatRequest,
    window: tuple[datetime, datetime] | None,
    budget: float,
    used_globally: set[str],
    max_minutes: int,
) -> None:
    """Swap out any stop you would reach after the door has shut.

    This has to run on the finished schedule rather than at selection: whether the museum is
    still open depends on where it lands in the running order, which isn't known until the
    durations and travel legs are settled. Each pass either fixes a stop or removes one, so
    the loop is bounded by the number of stops.
    """
    if window is None:
        return

    for _ in range(len(plan.stops) + 1):
        _normalize_schedule(plan, registry)
        shut = next(
            (
                stop
                for stop in plan.stops
                if not _stop_is_open_on_arrival(stop, registry, window)
            ),
            None,
        )
        if shut is None:
            return

        index = plan.stops.index(shut)
        arrival = window[0] + timedelta(minutes=shut.start_offset_minutes)
        plan.stops.pop(index)
        # This one slots back into the middle of a route, so both neighbours constrain it.
        replacement = _pick_candidate(
            plan,
            pool,
            request,
            window,
            budget,
            used_globally,
            registry,
            at_moment=arrival,
            before=plan.stops[index - 1] if index else None,
            after=plan.stops[index] if index < len(plan.stops) else None,
        )
        if replacement is not None:
            plan.stops.insert(index, replacement)
        if not plan.stops:
            return
        _recompute_travel(plan, registry, request.transportation)
        _assign_durations(plan, max_minutes, registry)


def _normalize_schedule(plan: Plan, registry: dict[str, dict]) -> None:
    """Recompute the timeline from durations so the schedule is always self-consistent.

    The clock starts when the user leaves, not when they arrive: offsetting the first stop by
    the walk to it is why the card no longer claims you teleport to a park nine minutes away.
    """
    offset = _origin_travel(plan, registry)
    plan.travel_time_minutes = offset

    for index, stop in enumerate(plan.stops):
        stop.start_offset_minutes = offset
        if index == len(plan.stops) - 1:
            stop.travel_minutes_to_next = 0
        offset += stop.duration_minutes + stop.travel_minutes_to_next
        plan.travel_time_minutes += stop.travel_minutes_to_next

    plan.total_duration_minutes = offset


# --- Pricing ----------------------------------------------------------------------------


def _format_cost(dollars: int) -> str:
    return "Free" if dollars <= 0 else f"~${dollars}"


def _price_plan(plan: Plan, request: ChatRequest) -> None:
    """Attach the same prices the model was shown, once the stop list is final.

    Still prefixed with "~": a cuisine tag separates the burger counter from the bistro, but it
    is a band, not a lookup, and quoting "$22" as though someone checked would be the same lie
    as "$8" -- only better calibrated.

    Must run after _fit_to_time, which can still drop stops. If a price ever starts depending
    on how long a stop is, it must stay after it for the same reason.
    """
    total = 0
    for stop in plan.stops:
        stop.estimated_cost = _format_cost(stop.cost_usd)
        total += stop.cost_usd

    if total <= 0:
        plan.estimated_cost = "Free"
        return
    per_person = request.companions.strip().lower() not in {"", "solo"}
    plan.estimated_cost = f"≈${total}{' pp' if per_person else ''}"


# --- Prose ------------------------------------------------------------------------------

# Words that describe a category rather than an outing. A title made only of these is the
# "Food and Drink" failure: technically accurate, tells the user nothing.
GENERIC_TITLE_WORDS = {
    "a", "adventure", "afternoon", "an", "and", "at", "bite", "bites", "break", "cafe",
    "cafes", "chill", "city", "coffee", "crawl", "culture", "day", "downtown", "drink",
    "drinks", "eat", "eating", "escape", "evening", "explore", "food", "for", "fun",
    "getaway", "hop", "hopping", "in", "landmark", "landmarks", "morning", "museum",
    "museums", "night", "of", "on", "outdoor", "outdoors", "outing", "park", "parks", "plan",
    "relaxed", "shopping", "sights", "some", "the", "time", "tour", "treats", "trip", "with",
    "your",
}

# Words that assert a kind of stop. Prose naming one the plan doesn't have is the tell that a
# stop was substituted underneath it -- "a dessert stop and a visit to a brewery" for a plan
# with no brewery.
KIND_WORDS = {
    "restaurant": MEAL, "dinner": MEAL, "lunch": MEAL, "brunch": MEAL, "breakfast": MEAL,
    "meal": MEAL, "supper": MEAL,
    "bite": QUICK_BITE, "snack": QUICK_BITE, "tacos": QUICK_BITE, "takeaway": QUICK_BITE,
    "cafe": CAFE, "coffee": CAFE, "espresso": CAFE, "latte": CAFE,
    "dessert": TREAT, "bakery": TREAT, "pastry": TREAT, "sweets": TREAT, "gelato": TREAT,
    "bar": DRINKS, "bars": DRINKS, "brewery": DRINKS, "pub": DRINKS, "beer": DRINKS,
    "cocktail": DRINKS, "cocktails": DRINKS, "drink": DRINKS, "drinks": DRINKS,
    "park": OUTDOOR, "garden": OUTDOOR, "gardens": OUTDOOR, "greenway": OUTDOOR,
    "museum": CULTURE, "gallery": CULTURE, "exhibit": CULTURE, "art": CULTURE,
    "culture": CULTURE, "cultural": CULTURE,
    "cinema": ACTIVITY, "movie": ACTIVITY, "film": ACTIVITY, "bowling": ACTIVITY,
    "show": ACTIVITY,
    "landmark": SIGHT, "monument": SIGHT, "statue": SIGHT,
    "bookstore": SHOPPING, "bookshop": SHOPPING, "books": SHOPPING, "shops": SHOPPING,
    "mall": SHOPPING, "boutique": SHOPPING,
}

TIME_WORDS = {
    "breakfast", "brunch", "lunch", "dinner", "supper", "nightcap", "morning",
    "afternoon", "evening", "night", "tonight", "sunset", "sunrise", "midnight",
}

COUNT_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", text.lower()))


def _title_is_generic(title: str) -> bool:
    words = _words(title)
    return not words or words <= GENERIC_TITLE_WORDS


def _named_places(text: str, names: set[str]) -> set[str]:
    lowered = text.lower()
    return {name for name in names if name.lower() in lowered}


def _claims_absent_kind(text: str, plan: Plan) -> bool:
    kinds = {stop.kind for stop in plan.stops}
    claimed = {KIND_WORDS[word] for word in _words(text) if word in KIND_WORDS}
    return bool(claimed - kinds)


def _summary_is_stale(
    plan: Plan,
    summary: str,
    pool_names: set[str],
    window: tuple[datetime, datetime] | None,
) -> bool:
    """True when the prose describes a plan we no longer have, or a time we can't vouch for."""
    stop_names = {stop.name for stop in plan.stops}
    mentioned = _named_places(summary, pool_names)
    if mentioned - stop_names:  # names a place that got substituted or dropped
        return True
    if len(mentioned & stop_names) >= 2:  # it's a list of the stops, not a description
        return True
    if _claims_absent_kind(summary, plan):  # promises a brewery this plan no longer has
        return True
    return _mentions_unknowable_time(summary, window)


def _mentions_unknowable_time(
    text: str, window: tuple[datetime, datetime] | None
) -> bool:
    used = _words(text) & TIME_WORDS
    if not used:
        return False
    if window is None:
        return True
    allowed = set(_meals_in_window(window))
    start_h, _ = _window_hours(window)
    allowed.add("morning" if start_h < 12 else "afternoon" if start_h < 17 else "evening")
    return bool(used - allowed - {"night", "tonight", "sunset", "sunrise", "midnight"})


def _fallback_title(plan: Plan) -> str:
    # A one-stop plan is that place, so the place name is the most specific title there is.
    if len(plan.stops) == 1:
        return plan.stops[0].name
    return f"{plan.stops[0].name}, then {_spec(plan.stops[-1]).phrase}"


def _minutes(count: int) -> str:
    return f"{count} minute" if count == 1 else f"{count} minutes"


def _fallback_summary(plan: Plan) -> str:
    phrases = _join([_spec(stop).phrase for stop in plan.stops])
    travel = plan.travel_time_minutes
    if len(plan.stops) == 1:
        away = f", about {_minutes(travel)} away" if travel else ""
        return f"One unhurried stop{away}: {phrases}, and nowhere else to be."
    tail = f", with about {_minutes(travel)} of travel in between" if travel else ""
    count = COUNT_WORDS.get(len(plan.stops), str(len(plan.stops)))
    return f"An easy {count}-stop run -- {phrases}{tail}."


def _fallback_reason(plan: Plan, request: ChatRequest) -> str:
    vibe = request.vibe.strip().lower() or "easygoing"
    closer = _spec(plan.stops[-1]).phrase
    return (
        f"It stays close together and finishes on {closer}, which is an easy fit for a "
        f"{vibe} outing."
    )


def _polish_prose(
    plans: list[Plan],
    request: ChatRequest,
    pool_names: set[str],
    window: tuple[datetime, datetime] | None,
) -> None:
    """Backstop the prose rules the prompt asks for but the model doesn't always honour.

    Rewriting here rather than re-prompting keeps generation to the one round trip the rest of
    this module is built around.
    """
    seen_titles: set[str] = set()
    for plan in plans:
        title = plan.title.strip()
        if (
            _title_is_generic(title)
            or title.lower() in seen_titles
            or _mentions_unknowable_time(title, window)
            or _claims_absent_kind(title, plan)
            or _named_places(title, pool_names) - {stop.name for stop in plan.stops}
        ):
            title = _fallback_title(plan)
        plan.title = title
        seen_titles.add(title.lower())

        if _summary_is_stale(plan, plan.summary, pool_names, window):
            plan.summary = _fallback_summary(plan)

        if _mentions_unknowable_time(plan.vibe_match_reason, window) or _named_places(
            plan.vibe_match_reason, pool_names
        ) - {stop.name for stop in plan.stops}:
            plan.vibe_match_reason = _fallback_reason(plan, request)


# --- Prompt assembly ---------------------------------------------------------------------


def _format_candidates(
    candidates: list[dict], window: tuple[datetime, datetime] | None
) -> str:
    lines = []
    for index, place in enumerate(candidates, start=1):
        spec = KIND_SPECS.get(place["kind"], FALLBACK_SPEC)
        cost = "free" if place["cost_usd"] <= 0 else f"about ${place['cost_usd']}"
        # Only shown when the place shuts before the outing ends -- that is precisely when the
        # model needs to put it early in the running order rather than last.
        closing = _closes_at(place.get("opening_hours", ""), window)
        shuts = f" | CLOSES {_clock(closing)}" if closing else ""
        lines.append(
            f"{index}. {place['name']} | {spec.label} | "
            f"{place['travel_minutes_from_origin']} min away | "
            f"about {spec.typical_minutes} min | {cost}{shuts}"
        )
    return "\n".join(lines)


def _budget_line(
    request: ChatRequest,
    candidates: list[dict],
    window: tuple[datetime, datetime] | None,
) -> str:
    """Spell out affordability using the prices of the actual candidates on offer.

    Read off the candidate list rather than KIND_SPECS so it can never contradict the numbers
    the model is choosing between: now that cuisine tags move prices per place, "a sit-down
    meal costs ~$25" would be wrong about both the burger counter and the bistro.
    """
    budget = int(request.budget)
    if budget <= 0:
        return "Budget: nothing to spend. Every stop you pick must be free."

    cheapest: dict[str, int] = {}
    for place in candidates:
        kind = place["kind"]
        if not place["cost_usd"] or not _kind_open_in_window(kind, window):
            continue
        cheapest[kind] = min(cheapest.get(kind, place["cost_usd"]), place["cost_usd"])

    fits = sorted(
        (cost, KIND_SPECS[kind].label) for kind, cost in cheapest.items() if cost <= budget
    )
    over = sorted(
        (cost, KIND_SPECS[kind].label) for kind, cost in cheapest.items() if cost > budget
    )

    line = f"Budget: about ${budget} per person for the whole outing."
    if fits:
        line += " Within reach: " + _join([f"{label} from ~${c}" for c, label in fits]) + "."
    if over:
        line += (
            " Out of reach entirely, so don't pick them: "
            + _join([f"{label} (cheapest ~${c})" for c, label in over])
            + "."
        )
    return (
        line + " Prices differ from place to place -- go by the number on each line, not by "
        "the kind of stop. Free stops cost nothing against it."
    )


def _time_lines(window: tuple[datetime, datetime] | None) -> str:
    if window is None:
        return (
            "The current local time is unknown, so never name a time of day or a meal: no "
            "breakfast, lunch, dinner, morning, afternoon or evening anywhere in the title, "
            "summary or reason.\n"
        )
    start, end = window
    meals = _meals_in_window(window)
    meal_line = (
        f"Mealtimes inside that window: {_join(meals)}. Nothing here is any other meal."
        if meals
        else "No mealtime falls inside that window, so don't call any stop a meal."
    )
    return (
        f"Now: {start.strftime('%A')} {_clock(start)}. "
        f"The plan runs {_clock(start)} to {_clock(end)}.\n"
        f"{meal_line}\n"
    )


def _user_message(
    request: ChatRequest,
    candidates: list[dict],
    window: tuple[datetime, datetime] | None,
) -> str:
    return (
        f"Nearby places you may use (ranked best first):\n"
        f"{_format_candidates(candidates, window)}\n\n"
        f"Current location: {request.current_location}\n"
        f"{_time_lines(window)}"
        f"Available time: {request.available_time} hours\n"
        f"Vibe: {request.vibe}\n"
        f"{_budget_line(request, candidates, window)}\n"
        f"Transportation: {request.transportation}\n"
        f"Energy level: {request.energy_level}\n"
        f"Companions: {request.companions}\n"
        f"Weather: {request.weather}\n"
        f"\n"
        f"Give every plan exactly {_target_stop_count(request)} stops, in the order they would "
        f"happen. Don't work out how long each stop takes or when it starts -- the app builds "
        f"the schedule from the kinds of places you pick.\n"
    )


def _invoke_with_retry(user_message: str, attempts: int = 3) -> dict:
    """Run the agent, retrying when the model emits a malformed structured response.

    Groq rejects these as 'tool_use_failed' 400s. It happens intermittently (roughly one
    call in five) and is not caused by the input, so simply asking again almost always
    succeeds. Rate limits are re-raised immediately -- retrying those only makes it worse.
    """
    for attempt in range(attempts):
        try:
            return agent.invoke(
                {"messages": [{"role": "user", "content": user_message}]}
            )
        except RateLimitError:
            raise
        except BadRequestError:
            if attempt == attempts - 1:
                raise
    raise AssertionError("unreachable")


def _build_plan(draft: PlanDraft, registry: dict[str, dict]) -> Plan:
    """Turn a draft into a real plan, keeping only names that match a verified place."""
    stops = []
    seen = set()
    for name in draft.stops:
        place = registry.get(name.strip().lower())
        if place is None or place["name"] in seen:
            continue
        seen.add(place["name"])
        stops.append(_stop_from_place(place))

    return Plan(
        title=draft.title,
        summary=draft.summary,
        stops=stops,
        vibe_match_reason=draft.vibe_match_reason,
        is_recommended=draft.is_recommended,
    )


def generate_plans(request: ChatRequest) -> PlansResponse:
    window = _plan_window(request)

    with _generation_lock:
        _place_registry.clear()

        origin = geocode_location.func(request.current_location)
        if "error" in origin:
            raise ValueError(
                f"Could not find '{request.current_location}': {origin['error']}"
            )

        radius_m = int(
            COMFORTABLE_DISTANCE_M.get(request.transportation.strip().lower(), 1200.0)
            * 2.5
        )
        candidates = _gather_candidates(
            origin["lat"],
            origin["lon"],
            request.transportation,
            request.energy_level,
            radius_m,
        )
        registry = dict(_place_registry)

        # Somewhere shut for the whole outing is not a suggestion. Dropping it here rather
        # than at selection means the model never sees it, so it can't build a plan around a
        # locked door and have the stop swapped out from under its own prose.
        candidates = [
            place
            for place in candidates
            if _open_during_window(place.get("opening_hours", ""), window)
        ]

        if not candidates:
            return PlansResponse(plans=[])

        result = _invoke_with_retry(_user_message(request, candidates, window))

    draft: PlansDraft = result["structured_response"]
    budget = max(request.budget, 0.0)
    max_minutes = max(SHORTEST_STOP_MINUTES, round(request.available_time * 60))
    pool_names = {place["name"] for place in candidates}
    used_globally: set[str] = set()
    seen_stops: set[frozenset[str]] = set()

    plans: list[Plan] = []
    for plan_draft in draft.plans:
        plan = _build_plan(plan_draft, registry)
        # Order matters: composition settles which stops exist, travel depends on which places
        # ended up adjacent, the fit can still drop or add stops, and only then are the
        # schedule and the price describing a list that won't change again.
        _enforce_composition(
            plan, candidates, registry, request, window, budget, used_globally
        )
        _recompute_travel(plan, registry, request.transportation)
        _fit_to_time(
            plan, max_minutes, candidates, registry, request, window, budget, used_globally
        )
        if not plan.stops:
            continue
        _relocate_outliers(
            plan, registry, candidates, request, window, budget, used_globally, max_minutes
        )
        _enforce_opening_hours(
            plan, registry, candidates, request, window, budget, used_globally, max_minutes
        )
        if not plan.stops:
            continue

        # Deduping has to come after every pass that can change the stop list, not before: two
        # plans that started out different can be relocated and re-timed onto the same places.
        if not _diversify(
            plan, seen_stops, candidates, registry, request, window, budget, used_globally
        ):
            continue
        # A swap above invalidates travel, durations, and its own opening hours.
        _recompute_travel(plan, registry, request.transportation)
        _assign_durations(plan, max_minutes, registry)
        _enforce_opening_hours(
            plan, registry, candidates, request, window, budget, used_globally, max_minutes
        )

        # Whatever that last round did, an identical card is never worth showing twice.
        signature = frozenset(stop.name for stop in plan.stops)
        if not plan.stops or signature in seen_stops:
            continue
        seen_stops.add(signature)
        _normalize_schedule(plan, registry)
        _price_plan(plan, request)
        plan.map_url = (
            "https://www.google.com/maps/search/?api=1&query="
            f"{quote(plan.stops[0].address)}"
        )
        used_globally.update(stop.name for stop in plan.stops)
        plans.append(plan)

    _polish_prose(plans, request, pool_names, window)

    # Exactly one recommendation, even if the model flagged zero or several.
    recommended = [plan for plan in plans if plan.is_recommended]
    if len(recommended) != 1 and plans:
        for plan in plans:
            plan.is_recommended = False
        (recommended[0] if recommended else plans[0]).is_recommended = True

    return PlansResponse(plans=plans)


def _describe(plans: PlansResponse) -> None:
    signatures = [frozenset(stop.name for stop in plan.stops) for plan in plans.plans]
    assert len(signatures) == len(set(signatures)), "two plans offer the same stops"
    for plan in plans.plans:
        flag = " *" if plan.is_recommended else ""
        print(f"\n{plan.title}{flag} -- {plan.estimated_cost}")
        print(f"  {plan.summary}")
        for stop in plan.stops:
            print(
                f"  {stop.start_offset_minutes:>4}m  {stop.name} "
                f"[{stop.kind}] {stop.duration_minutes}m {stop.estimated_cost}"
                + (f" -> {stop.travel_minutes_to_next}m" if stop.travel_minutes_to_next else "")
            )
        kinds = [stop.kind for stop in plan.stops]
        consumption = sum(1 for kind in kinds if kind in CONSUMPTION_KINDS)
        assert len(kinds) == len(set(kinds)), f"repeated kind: {kinds}"
        assert consumption <= MAX_CONSUMPTION_STOPS, f"too much eating: {kinds}"
        assert all(stop.duration_minutes % 5 == 0 for stop in plan.stops), "ragged duration"
        print(f"  total {plan.total_duration_minutes}m, moving {plan.travel_time_minutes}m")


if __name__ == "__main__":
    scenarios = [
        ChatRequest(
            current_location="Kellogg Blvd E, St. Paul, MN",
            available_time=3,
            vibe="Chill",
            budget=15,
            transportation="Walk",
            energy_level="Medium",
            companions="Solo",
            weather="78F, clear sky",
            local_time="2026-08-05 15:51:00",
        ),
        ChatRequest(
            current_location="Kellogg Blvd E, St. Paul, MN",
            available_time=1,
            vibe="Scenic",
            budget=0,
            transportation="Walk",
            energy_level="Low",
            companions="Partner",
            weather="61F, light rain",
            local_time="2026-08-05 09:15:00",
        ),
        ChatRequest(
            current_location="Kellogg Blvd E, St. Paul, MN",
            available_time=4,
            vibe="Social",
            budget=80,
            transportation="Drive",
            energy_level="High",
            companions="Friends",
            weather="70F, clear sky",
            local_time="2026-08-05 18:30:00",
        ),
    ]
    for scenario in scenarios:
        print(f"\n=== {scenario.vibe} / ${scenario.budget:.0f} / "
              f"{scenario.available_time}h / {scenario.local_time} ===")
        _describe(generate_plans(scenario))
