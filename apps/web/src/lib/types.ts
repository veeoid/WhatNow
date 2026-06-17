export type Stop = {
	name: string;
	category: string;
	durationMinutes: number;
	estimatedCost: string;
};

export type Plan = {
	type: "Lowest Effort" | "Best Match" | "More Fun";
	title: string;
	summary: string;
	stops: Stop[];
	totalDurationMinutes: number;
	travelTimeMinutes: number;
	estimatedCost: string;
	vibeMatchReason: string;
	mapUrl: string;
};
