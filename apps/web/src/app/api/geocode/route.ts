import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
	const text = request.nextUrl.searchParams.get("text");
	if (!text) {
		return NextResponse.json(
			{ error: "Missing 'text' query parameter" },
			{ status: 400 },
		);
	}

	const response = await fetch(
		`https://api.geoapify.com/v1/geocode/search?text=${encodeURIComponent(
			text,
		)}&format=json&apiKey=${process.env.GEO_API_KEY}`,
	);
	if (!response.ok) {
		const errorText = await response.text();
		return NextResponse.json({ error: errorText }, { status: response.status });
	}

	const data = await response.json();
	return NextResponse.json(data);
}
