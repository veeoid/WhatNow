import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
	const lat = request.nextUrl.searchParams.get("lat");
	const lng = request.nextUrl.searchParams.get("lng");
	if (!lat || !lng) {
		return NextResponse.json(
			{ error: "Missing 'lat'/'lng' query parameters" },
			{ status: 400 },
		);
	}

	const response = await fetch(
		`https://api.geoapify.com/v1/geocode/reverse?lat=${lat}&lon=${lng}&format=json&apiKey=${process.env.GEO_API_KEY}`,
	);
	if (!response.ok) {
		const errorText = await response.text();
		return NextResponse.json({ error: errorText }, { status: response.status });
	}

	const data = await response.json();
	return NextResponse.json(data);
}
