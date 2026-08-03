import { NextRequest, NextResponse } from "next/server";

// Plan generation runs ~12s and can take longer. Without this the hosting platform's
// default function timeout (often 10-15s) kills the request before the backend answers.
export const maxDuration = 60;

const BUDGET_DOLLARS: Record<string, number> = {
	Free: 0,
	Cheap: 15,
	Flexible: 40,
	Expensive: 80,
};

const TIME_HOURS: Record<string, number> = {
	"1 hour": 1,
	"2 hours": 2,
	"3 hours": 3,
	"Half day": 4,
};

const WEATHER_DESCRIPTIONS: Record<number, string> = {
	0: "clear sky",
	1: "mostly clear",
	2: "partly cloudy",
	3: "overcast",
	45: "fog",
	48: "depositing rime fog",
	51: "light drizzle",
	53: "moderate drizzle",
	55: "dense drizzle",
	61: "light rain",
	63: "moderate rain",
	65: "heavy rain",
	71: "light snow",
	73: "moderate snow",
	75: "heavy snow",
	80: "light rain showers",
	81: "moderate rain showers",
	82: "violent rain showers",
	95: "thunderstorm",
};

type BackendStop = {
	name: string;
	category: string;
	address: string;
	start_offset_minutes: number;
	duration_minutes: number;
	travel_minutes_to_next: number;
	estimated_cost: string;
};

type BackendPlan = {
	title: string;
	summary: string;
	stops: BackendStop[];
	total_duration_minutes: number;
	travel_time_minutes: number;
	estimated_cost: string;
	vibe_match_reason: string;
	is_recommended: boolean;
	map_url: string;
};

async function geocode(text: string): Promise<{ lat: number; lon: number } | null> {
	try {
		const response = await fetch(
			`https://api.geoapify.com/v1/geocode/search?text=${encodeURIComponent(
				text,
			)}&format=json&apiKey=${process.env.GEO_API_KEY}`,
		);
		if (!response.ok) return null;
		const data = await response.json();
		const top = data.results?.[0];
		return top ? { lat: top.lat, lon: top.lon } : null;
	} catch {
		return null;
	}
}

async function fetchWeatherSummary(lat: number, lon: number): Promise<string> {
	try {
		const response = await fetch(
			`https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,weather_code&temperature_unit=fahrenheit`,
		);
		if (!response.ok) return "";
		const data = await response.json();
		const temp = data.current?.temperature_2m;
		const description = WEATHER_DESCRIPTIONS[data.current?.weather_code] ?? "";
		if (temp === undefined) return "";
		return description ? `${Math.round(temp)}°F, ${description}` : `${Math.round(temp)}°F`;
	} catch {
		return "";
	}
}

export async function POST(request: NextRequest) {
	const body = await request.json();
	const {
		location,
		timeChoice,
		moodChoice,
		budgetChoice,
		transportChoice,
		energyChoice,
		companionsChoice,
	} = body;

	if (!location) {
		return NextResponse.json({ error: "Missing location" }, { status: 400 });
	}

	const coords = await geocode(location);
	const weather = coords ? await fetchWeatherSummary(coords.lat, coords.lon) : "";

	const backendPayload = {
		current_location: location,
		available_time: TIME_HOURS[timeChoice] ?? 3,
		vibe: moodChoice,
		budget: BUDGET_DOLLARS[budgetChoice] ?? 20,
		transportation: transportChoice,
		energy_level: energyChoice,
		companions: companionsChoice || "Solo",
		weather,
	};

	const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:5000";

	let response: Response;
	try {
		response = await fetch(`${backendUrl}/plan`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(backendPayload),
			signal: AbortSignal.timeout(60_000),
		});
	} catch {
		return NextResponse.json(
			{ error: "Could not reach the planning service. Is the backend running?" },
			{ status: 502 },
		);
	}

	if (!response.ok) {
		// The backend sends {error} JSON, but an unhandled crash yields an HTML page --
		// never surface that raw to the user.
		const message = await response
			.json()
			.then((body) => body.error)
			.catch(() => null);
		return NextResponse.json(
			{ error: message ?? "Couldn't build plans just now. Please try again." },
			{ status: response.status },
		);
	}

	const data: { plans: BackendPlan[] } = await response.json();

	const plans = data.plans.map((plan) => ({
		title: plan.title,
		summary: plan.summary,
		stops: plan.stops.map((stop) => ({
			name: stop.name,
			category: stop.category,
			address: stop.address,
			startOffsetMinutes: stop.start_offset_minutes,
			durationMinutes: stop.duration_minutes,
			travelMinutesToNext: stop.travel_minutes_to_next,
			estimatedCost: stop.estimated_cost,
		})),
		totalDurationMinutes: plan.total_duration_minutes,
		travelTimeMinutes: plan.travel_time_minutes,
		estimatedCost: plan.estimated_cost,
		vibeMatchReason: plan.vibe_match_reason,
		isRecommended: plan.is_recommended,
		mapUrl: plan.map_url,
	}));

	return NextResponse.json({ plans });
}
