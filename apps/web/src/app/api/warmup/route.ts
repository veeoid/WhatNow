import { NextResponse } from "next/server";
import { getBackendUrl } from "@/lib/backend";

// Free hosting tiers sleep the backend after ~15 minutes idle, and waking it takes ~50s.
// The page pings this on load so the backend is awake by the time someone submits the form,
// instead of the first request eating the cold start and timing out.
export const maxDuration = 60;

export async function GET() {
	try {
		const response = await fetch(`${getBackendUrl()}/health`, {
			cache: "no-store",
			signal: AbortSignal.timeout(55_000),
		});
		return NextResponse.json({ awake: response.ok });
	} catch {
		return NextResponse.json({ awake: false });
	}
}
