"use client";

import { useState } from "react";
import { Plan } from "@/lib/types";

type PlanCardProps = {
	plan: Plan;
	startTime: Date;
};

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
			className={`flex h-full flex-col overflow-hidden rounded-2xl bg-paper-card transition-shadow ${
				plan.isRecommended
					? "shadow-[0_2px_8px_rgba(38,38,36,0.06),0_16px_40px_-20px_rgba(38,38,36,0.28)] ring-1 ring-clay-300"
					: "shadow-[0_1px_3px_rgba(38,38,36,0.05),0_10px_28px_-18px_rgba(38,38,36,0.18)]"
			}`}
		>
			{plan.isRecommended && (
				<div className="bg-clay-50 px-6 py-2.5">
					<p className="font-mono text-[10px] uppercase tracking-[0.18em] text-clay-600">
						Our pick
					</p>
				</div>
			)}

			<div className="flex flex-1 flex-col p-6">
				<div className="flex items-baseline justify-between gap-3">
					<h3 className="text-[21px] font-light leading-[1.2] tracking-tight text-ink-900">
						{plan.title}
					</h3>
					<span className="tnum shrink-0 font-mono text-xs text-ink-500">
						{plan.estimatedCost}
					</span>
				</div>
				<p className="mt-2.5 text-[13px] font-light leading-relaxed text-ink-500">
					{plan.summary}
				</p>

				<div className="tnum mt-4 flex flex-wrap gap-1.5">
					<span className="rounded-full bg-paper-alt px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-ink-700">
						{formatDuration(plan.totalDurationMinutes)}
					</span>
					<span className="rounded-full bg-paper-alt px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-ink-500">
						{formatDuration(plan.travelTimeMinutes)} moving
					</span>
					<span className="rounded-full bg-paper-alt px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-ink-500">
						{plan.stops.length} stops
					</span>
				</div>

				{/* Itinerary, read as a timetable: time column, route line, stop */}
				<ol className="mt-5">
					{plan.stops.map((stop, index) => (
						<li key={`${stop.name}-${index}`}>
							<div className="flex gap-3">
								<div className="tnum w-[46px] shrink-0 pt-[3px] text-right font-mono text-[11px] text-ink-500">
									{formatClock(startTime, stop.startOffsetMinutes)}
								</div>
								<div className="flex w-5 flex-col items-center">
									<span
										className={`tnum flex h-5 w-5 shrink-0 items-center justify-center rounded-full font-mono text-[10px] ${
											plan.isRecommended
												? "bg-clay-400 text-white"
												: "bg-sage-700 text-white"
										}`}
									>
										{index + 1}
									</span>
									{index < plan.stops.length - 1 && (
										<span className="w-px flex-1 bg-rule" />
									)}
								</div>
								<div className="min-w-0 flex-1 pb-0.5">
									<p className="truncate text-sm leading-5 text-ink-900">
										{stop.name}
									</p>
									<p className="tnum mt-0.5 font-mono text-[11px] text-ink-500">
										{formatCategory(stop.category)} ·{" "}
										{formatDuration(stop.durationMinutes)} ·{" "}
										{stop.estimatedCost}
									</p>
								</div>
							</div>
							{stop.travelMinutesToNext > 0 && (
								<div className="flex gap-3">
									<div className="w-[46px] shrink-0" />
									<div className="flex w-5 flex-col items-center">
										<span className="w-px flex-1 bg-rule" />
									</div>
									<p className="flex-1 py-1.5 font-mono text-[10px] uppercase tracking-wider text-ink-500/70">
										{formatDuration(stop.travelMinutesToNext)} on foot
									</p>
								</div>
							)}
						</li>
					))}
				</ol>

				<p className="mt-auto pt-5 text-[13px] font-light leading-relaxed text-ink-500">
					{plan.vibeMatchReason}
				</p>

				<div className="mt-5 flex gap-2">
					<a
						href={plan.mapUrl}
						target="_blank"
						rel="noreferrer"
						className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-full bg-ink-900 px-5 py-2.5 text-[13px] font-medium text-white transition hover:bg-[#3a3a37]"
					>
						Open in maps
					</a>
					<button
						type="button"
						onClick={() => setSaved(!saved)}
						aria-pressed={saved}
						className={`inline-flex shrink-0 items-center justify-center rounded-full border px-5 py-2.5 text-[13px] font-medium transition ${
							saved
								? "border-clay-300 bg-clay-50 text-clay-600"
								: "border-rule bg-transparent text-ink-700 hover:bg-paper-alt"
						}`}
					>
						{saved ? "Saved" : "Save"}
					</button>
				</div>
			</div>
		</article>
	);
}
