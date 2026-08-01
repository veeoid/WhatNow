"use client";

import { useState, useCallback } from "react";

type Coords = { lat: number; lng: number };
export type LocationStatus = "idle" | "loading" | "success" | "error";

export function useCurrentLocation() {
	const [coords, setCoords] = useState<Coords | null>(null);
	const [status, setStatus] = useState<LocationStatus>("idle");
	const [error, setError] = useState<string | null>(null);

	const request = useCallback((onSuccess?: (coords: Coords) => void) => {
		if (typeof navigator === "undefined" || !navigator.geolocation) {
			setStatus("error");
			setError("Location isn't supported here — type your city instead.");
			return;
		}
		setStatus("loading");
		setError(null);
		navigator.geolocation.getCurrentPosition(
			(pos) => {
				const nextCoords = {
					lat: pos.coords.latitude,
					lng: pos.coords.longitude,
				};
				setCoords(nextCoords);
				setStatus("success");
				onSuccess?.(nextCoords);
			},
			(err) => {
				const messages: Record<number, string> = {
					1: "Permission denied — type your city instead.",
					2: "Couldn't pin your location — type your city instead.",
					3: "Location timed out — type your city instead.",
				};
				setStatus("error");
				setError(messages[err.code] ?? "Couldn't get your location.");
			},
			{ enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 },
		);
	}, []);

	return { coords, status, error, request };
}
