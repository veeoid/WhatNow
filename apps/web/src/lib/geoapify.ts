export type GeoapifyGeocodeResponse = {
	results: { formatted: string }[];
};

export async function getGeocode(
	address: string,
	signal?: AbortSignal,
): Promise<GeoapifyGeocodeResponse> {
	const response = await fetch(
		`/api/geocode?text=${encodeURIComponent(address)}`,
		{ signal },
	);
	if (!response.ok) {
		const errorText = await response.text();
		throw new Error(
			`Failed to fetch geocode data: ${response.statusText} - ${errorText}`,
		);
	}
	return response.json();
}

export async function getReverseGeocode(
	lat: number,
	lng: number,
	signal?: AbortSignal,
): Promise<GeoapifyGeocodeResponse> {
	const response = await fetch(
		`/api/geocode/reverse?lat=${lat}&lng=${lng}`,
		{ signal },
	);
	if (!response.ok) {
		const errorText = await response.text();
		throw new Error(
			`Failed to fetch reverse geocode data: ${response.statusText} - ${errorText}`,
		);
	}
	return response.json();
}
