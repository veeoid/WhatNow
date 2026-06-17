import { Plan } from "@/lib/types";

export const mockPlans: Plan[] = [
	{
		type: "Lowest Effort",
		title: "Coffee, bookstore, and a short walk",
		summary:
			"A calm nearby plan when you want to get out without doing too much.",
		stops: [
			{
				name: "Neighborhood Coffee Shop",
				category: "Cafe",
				durationMinutes: 35,
				estimatedCost: "$6-12",
			},
			{
				name: "Local Bookstore",
				category: "Bookstore",
				durationMinutes: 40,
				estimatedCost: "$0-20",
			},
		],
		totalDurationMinutes: 110,
		travelTimeMinutes: 18,
		estimatedCost: "$10-30",
		vibeMatchReason:
			"Short travel, flexible timing, and no reservation needed.",
		mapUrl: "https://maps.google.com/",
	},
	{
		type: "Best Match",
		title: "Scenic walk and casual dinner",
		summary: "A balanced plan with fresh air, food, and a relaxed pace.",
		stops: [
			{
				name: "Waterfront Walk",
				category: "Scenic",
				durationMinutes: 50,
				estimatedCost: "Free",
			},
			{
				name: "Casual Dinner Spot",
				category: "Restaurant",
				durationMinutes: 60,
				estimatedCost: "$18-30",
			},
		],
		totalDurationMinutes: 150,
		travelTimeMinutes: 25,
		estimatedCost: "$20-35",
		vibeMatchReason:
			"Good mix of movement, scenery, and food without feeling rushed.",
		mapUrl: "https://maps.google.com/",
	},
	{
		type: "More Fun",
		title: "Arcade, dessert, and late-night stroll",
		summary:
			"A more playful option if you want the evening to feel less routine.",
		stops: [
			{
				name: "Arcade Bar",
				category: "Entertainment",
				durationMinutes: 70,
				estimatedCost: "$15-25",
			},
			{
				name: "Dessert Spot",
				category: "Dessert",
				durationMinutes: 30,
				estimatedCost: "$8-15",
			},
		],
		totalDurationMinutes: 160,
		travelTimeMinutes: 30,
		estimatedCost: "$25-45",
		vibeMatchReason:
			"More energy and novelty while still staying realistic for a few hours.",
		mapUrl: "https://maps.google.com/",
	},
];
