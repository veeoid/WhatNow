export type GeoapifyGeocodeResponse = {
	results: { formatted: string }[];
};

export async function getGeocode(
	address: string,
	signal?: AbortSignal,
): Promise<GeoapifyGeocodeResponse> {
	const response = await fetch(
		`https://api.geoapify.com/v1/geocode/search?text=${encodeURIComponent(
			address,
		)}&format=json&apiKey=${process.env.NEXT_PUBLIC_GEOAPIFY_API_KEY}`,
		{ signal },
	);
	if (!response.ok) {
		const errorText = await response.text();
		throw new Error(
			`Failed to fetch Geoapify geocode data: ${response.statusText} - ${errorText}`,
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
		`https://api.geoapify.com/v1/geocode/reverse?lat=${lat}&lon=${lng}&format=json&apiKey=${process.env.NEXT_PUBLIC_GEOAPIFY_API_KEY}`,
		{ signal },
	);
	if (!response.ok) {
		const errorText = await response.text();
		throw new Error(
			`Failed to fetch Geoapify reverse geocode data: ${response.statusText} - ${errorText}`,
		);
	}
	return response.json();
}
