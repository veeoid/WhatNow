export type Stop = {
	name: string;
	category: string;
	address: string;
	startOffsetMinutes: number;
	durationMinutes: number;
	travelMinutesToNext: number;
	estimatedCost: string;
};

export type Plan = {
	title: string;
	summary: string;
	stops: Stop[];
	totalDurationMinutes: number;
	travelTimeMinutes: number;
	estimatedCost: string;
	vibeMatchReason: string;
	isRecommended: boolean;
	mapUrl: string;
};
