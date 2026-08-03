import { NextResponse } from "next/server";

// Free hosting tiers sleep the backend after ~15 minutes idle, and waking it takes ~50s.
// The page pings this on load so the backend is awake by the time someone submits the form,
// instead of the first request eating the cold start and timing out.
export const maxDuration = 60;

export async function GET() {
	const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:5001";

	try {
		const response = await fetch(`${backendUrl}/health`, {
			cache: "no-store",
			signal: AbortSignal.timeout(55_000),
		});
		return NextResponse.json({ awake: response.ok });
	} catch {
		return NextResponse.json({ awake: false });
	}
}
