import os
from math import atan2, cos, radians, sin, sqrt
from typing import Literal
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


class Stop(BaseModel):
    name: str
    category: str
    address: str
    duration_minutes: int
    estimated_cost: str


class Plan(BaseModel):
    type: Literal["Lowest Effort", "Best Match", "More Fun"]
    title: str
    summary: str
    stops: list[Stop]
    total_duration_minutes: int
    travel_time_minutes: int
    estimated_cost: str
    vibe_match_reason: str
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


@tool
def search_nearby_places(
    lat: float,
    lon: float,
    categories: str,
    radius_m: int = 3000,
    limit: int = 10,
) -> list[dict]:
    """Search for real, currently-existing venues near a coordinate.

    categories: comma-separated Geoapify category codes, e.g. "catering.cafe",
    "catering.restaurant", "catering.bar", "catering.fast_food", "entertainment.museum",
    "entertainment.cinema", "entertainment.bowling_alley", "leisure.park",
    "tourism.attraction", "tourism.sights", "commercial.shopping_mall", "sport.fitness".
    Call this more than once with different categories to gather different kinds of
    stops for a plan.
    radius_m: search radius in meters (default 3000, about 2 miles).

    Returns real places with name, address, distance in meters, and categories.
    Only use place names returned here in your final answer -- never invent a place.
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
        distance_m = (
            round(_distance_meters(lat, lon, place_lat, place_lon))
            if place_lat is not None and place_lon is not None
            else None
        )
        places.append(
            {
                "name": props.get("name") or props.get("address_line1", "Unknown"),
                "address": props.get("formatted", ""),
                "distance_m": distance_m,
                "categories": props.get("categories", []),
            }
        )
    return places


SYSTEM_PROMPT = """
You are a planning assistant for WhatNow, an app that suggests real things to do right now.

You have two tools:
- geocode_location: turn a free-text location into coordinates. Always call this first for
  the user's current_location.
- search_nearby_places: find real, currently-existing venues near a coordinate. Call it one
  or more times with different Geoapify categories to gather candidate stops (cafes,
  restaurants, parks, entertainment, shopping, etc.) that match the user's vibe, budget, and
  energy level.

Rules:
- Never invent a place name or address. Only use places returned by search_nearby_places,
  copied exactly as given.
- Respect the user's available_time: total_duration_minutes (all stops plus travel) must fit
  within it.
- Respect budget and transportation: don't suggest an expensive dinner for a "cheap" budget,
  and keep travel realistic for the given transportation mode.
- Produce exactly three plans:
  - "Lowest Effort": minimal travel and effort, easiest to just go do right now.
  - "Best Match": the plan that best fits the user's stated vibe, budget, and energy overall.
  - "More Fun": a more adventurous or higher-energy option than Best Match.
- Each plan needs 1-3 real stops with realistic per-stop durations and cost estimates, a short
  summary, and a one-sentence vibe_match_reason explaining why it fits.
"""


llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.3)

agent = create_agent(
    model=llm,
    tools=[geocode_location, search_nearby_places],
    system_prompt=SYSTEM_PROMPT,
    response_format=PlansResponse,
)


def _user_message(request: ChatRequest) -> str:
    return (
        f"Current location: {request.current_location}\n"
        f"Available time: {request.available_time} hours\n"
        f"Vibe: {request.vibe}\n"
        f"Budget: ${request.budget}\n"
        f"Transportation: {request.transportation}\n"
        f"Energy level: {request.energy_level}\n"
        f"Companions: {request.companions}\n"
        f"Weather: {request.weather}\n"
    )


def generate_plans(request: ChatRequest) -> PlansResponse:
    result = agent.invoke(
        {"messages": [{"role": "user", "content": _user_message(request)}]}
    )
    response: PlansResponse = result["structured_response"]

    for plan in response.plans:
        if plan.stops:
            plan.map_url = (
                "https://www.google.com/maps/search/?api=1&query="
                f"{quote(plan.stops[0].address)}"
            )

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
