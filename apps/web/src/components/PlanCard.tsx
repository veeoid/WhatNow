"use client";

import { useState } from "react";
import { Plan } from "@/lib/types";

type PlanCardProps = {
	plan: Plan;
	startTime: Date;
};

const categoryEmoji: Record<string, string> = {
	cafe: "☕",
	coffee: "☕",
	restaurant: "🍽️",
	fast_food: "🍔",
	food_court: "🍜",
	bar: "🍸",
	pub: "🍺",
	ice_cream: "🍦",
	bakery: "🥐",
	park: "🌳",
	garden: "🌷",
	museum: "🏛️",
	gallery: "🖼️",
	cinema: "🎬",
	theatre: "🎭",
	bowling_alley: "🎳",
	arcade: "🕹️",
	books: "📚",
	mall: "🛍️",
	attraction: "✨",
	sights: "📸",
	viewpoint: "🌄",
	fitness: "💪",
};

function emojiFor(category: string): string {
	const parts = category.toLowerCase().split(".").reverse();
	for (const part of parts) {
		if (categoryEmoji[part]) return categoryEmoji[part];
	}
	return "📍";
}

function formatCategory(category: string): string {
	const leaf = category.split(".").pop() ?? category;
	return leaf.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatClock(start: Date, offsetMinutes: number): string {
	const time = new Date(start.getTime() + offsetMinutes * 60_000);
	return time.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatDuration(minutes: number): string {
	const hours = Math.floor(minutes / 60);
	const mins = minutes % 60;
	if (hours === 0) return `${mins}m`;
	return mins === 0 ? `${hours}h` : `${hours}h ${mins}m`;
}

export default function PlanCard({ plan, startTime }: PlanCardProps) {
	const [saved, setSaved] = useState(false);

	return (
		<article
			className={`flex h-full flex-col overflow-hidden rounded-3xl border bg-white transition ${
				plan.isRecommended
					? "border-sage-400 shadow-[0_2px_16px_rgba(47,74,52,0.12),0_1px_4px_rgba(0,0,0,0.04)]"
					: "border-sage-200 shadow-sm"
			}`}
		>
			{plan.isRecommended && (
				<div className="bg-sage-100 px-5 py-2.5 text-center">
					<p className="text-[11px] font-semibold uppercase tracking-widest text-sage-700">
						★ Our Recommendation
					</p>
				</div>
			)}

			<div className="flex flex-1 flex-col p-5">
				<div className="flex items-start justify-between gap-3">
					<h3 className="text-[17px] font-semibold leading-snug text-stone-950">
						{plan.title}
					</h3>
					<span className="shrink-0 rounded-full bg-sage-100 px-2.5 py-1 text-xs font-semibold text-sage-700">
						{plan.estimatedCost}
					</span>
				</div>
				<p className="mt-1.5 text-sm leading-relaxed text-stone-500">
					{plan.summary}
				</p>

				<div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-500">
					<span>
						🕒 {formatClock(startTime, 0)} –{" "}
						{formatClock(startTime, plan.totalDurationMinutes)}
					</span>
					<span>⏱ {formatDuration(plan.totalDurationMinutes)} total</span>
					<span>🚶 {formatDuration(plan.travelTimeMinutes)} travel</span>
				</div>

				{/* Timeline */}
				<ol className="mt-4 space-y-0">
					{plan.stops.map((stop, index) => (
						<li key={`${stop.name}-${index}`}>
							<div className="flex gap-3">
								<div className="flex w-[52px] shrink-0 justify-end pt-2.5">
									<span className="text-xs font-medium tabular-nums text-stone-500">
										{formatClock(startTime, stop.startOffsetMinutes)}
									</span>
								</div>
								<div className="flex flex-col items-center">
									<span className="mt-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-sage-100 text-sm">
										{emojiFor(stop.category)}
									</span>
									{index < plan.stops.length - 1 && (
										<span className="w-px flex-1 bg-sage-200" />
									)}
								</div>
								<div className="min-w-0 flex-1 pb-1 pt-1.5">
									<div className="rounded-2xl bg-sage-50 px-3.5 py-2.5">
										<p className="truncate text-sm font-medium text-stone-900">
											{stop.name}
										</p>
										<p className="mt-0.5 text-xs text-stone-400">
											{formatCategory(stop.category)} ·{" "}
											{formatDuration(stop.durationMinutes)} ·{" "}
											{stop.estimatedCost}
										</p>
									</div>
								</div>
							</div>
							{stop.travelMinutesToNext > 0 && (
								<div className="flex gap-3">
									<div className="w-[52px] shrink-0" />
									<div className="flex w-7 flex-col items-center">
										<span className="w-px flex-1 bg-sage-200" />
									</div>
									<p className="flex-1 py-1 text-[11px] text-stone-400">
										{formatDuration(stop.travelMinutesToNext)} travel
									</p>
								</div>
							)}
						</li>
					))}
				</ol>

				<div className="mt-4 rounded-2xl bg-sage-50 p-3.5">
					<p className="text-[10px] font-semibold uppercase tracking-wider text-sage-500">
						Why it fits
					</p>
					<p className="mt-1 text-sm leading-relaxed text-stone-700">
						{plan.vibeMatchReason}
					</p>
				</div>

				<div className="mt-4 flex gap-2.5 pt-1">
					<a
						href={plan.mapUrl}
						target="_blank"
						rel="noreferrer"
						className="inline-flex flex-1 items-center justify-center rounded-full bg-sage-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-sage-800 active:scale-[0.98]"
					>
						Open map
					</a>
					<button
						type="button"
						onClick={() => setSaved(!saved)}
						aria-pressed={saved}
						className={`inline-flex shrink-0 items-center justify-center rounded-full border px-4 py-2.5 text-sm font-semibold transition active:scale-[0.98] ${
							saved
								? "border-sage-200 bg-sage-100 text-sage-600"
								: "border-sage-200 bg-white text-stone-900 hover:border-sage-300 hover:bg-sage-50"
						}`}
					>
						{saved ? "✓ Saved" : "Save"}
					</button>
				</div>
			</div>
		</article>
	);
}
