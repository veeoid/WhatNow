"use client";

import { useEffect, useRef } from "react";
import ChoicePill from "@/components/ChoicePill";
import { LocationStatus } from "@/lib/useCurrentLocation";

type InputSectionProps = {
	location: string;
	onLocationChange: (value: string) => void;
	onLocationSelect: (value: string) => void;
	onDismissSuggestions: () => void;
	locSuggestions: string[];
	timeChoice: string;
	setTimeChoice: (value: string) => void;
	moodChoice: string;
	setMoodChoice: (value: string) => void;
	budgetChoice: string;
	setBudgetChoice: (value: string) => void;
	transportChoice: string;
	setTransportChoice: (value: string) => void;
	energyChoice: string;
	setEnergyChoice: (value: string) => void;
	companionsChoice: string;
	setCompanionsChoice: (value: string) => void;
	onUseCurrentLocation: () => void;
	locationStatus: LocationStatus;
	locationError: string | null;
	onGenerate: () => void;
	isGenerating: boolean;
};

const timeOptions = ["1 hour", "2 hours", "3 hours", "Half day"];
const moodOptions = [
	"Chill",
	"Scenic",
	"Foodie",
	"Social",
	"Date",
	"Low energy",
	"Adventure",
];
const budgetOptions = ["Free", "Cheap", "Flexible", "Expensive"];
const transportOptions = ["Walk", "Transit", "Drive", "Rideshare"];
const energyOptions = ["Low", "Medium", "High"];
const companionsOptions = ["Solo", "Partner", "Friends", "Family"];

export default function InputSection({
	location,
	onLocationChange,
	onLocationSelect,
	onDismissSuggestions,
	onUseCurrentLocation,
	locSuggestions,
	locationStatus,
	locationError,
	timeChoice,
	setTimeChoice,
	moodChoice,
	setMoodChoice,
	budgetChoice,
	setBudgetChoice,
	transportChoice,
	setTransportChoice,
	energyChoice,
	setEnergyChoice,
	companionsChoice,
	setCompanionsChoice,
	onGenerate,
	isGenerating,
}: InputSectionProps) {
	const locationFieldRef = useRef<HTMLDivElement>(null);
	const hasSuggestions = locSuggestions.length > 0;

	// The dropdown floats over the controls below it, so it has to close on an outside
	// click or those controls can't be reached.
	useEffect(() => {
		if (!hasSuggestions) return;
		const handlePointerDown = (event: MouseEvent | TouchEvent) => {
			if (!locationFieldRef.current?.contains(event.target as Node)) {
				onDismissSuggestions();
			}
		};
		const handleKeyDown = (event: KeyboardEvent) => {
			if (event.key === "Escape") onDismissSuggestions();
		};
		document.addEventListener("mousedown", handlePointerDown);
		document.addEventListener("touchstart", handlePointerDown);
		document.addEventListener("keydown", handleKeyDown);
		return () => {
			document.removeEventListener("mousedown", handlePointerDown);
			document.removeEventListener("touchstart", handlePointerDown);
			document.removeEventListener("keydown", handleKeyDown);
		};
	}, [hasSuggestions, onDismissSuggestions]);

	return (
		<section className="rounded-2xl bg-paper-card p-7 shadow-[0_1px_3px_rgba(38,38,36,0.05),0_10px_28px_-18px_rgba(38,38,36,0.18)] sm:p-8">
			<div className="space-y-6">
				{/* Location */}
				<div className="space-y-2">
					<p className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-500">Where are you?</p>
					<div className="relative" ref={locationFieldRef}>
						<input
							value={location}
							onChange={(e) => onLocationChange(e.target.value)}
							className="w-full rounded-full border border-rule bg-transparent px-4 py-3 text-[15px] font-light text-ink-900 placeholder:text-ink-500/60 transition focus:border-ink-500/50 focus:outline-none"
							placeholder="Enter your location"
						/>
						{locSuggestions && locSuggestions.length > 0 && (
							<ul className="absolute z-10 mt-1.5 w-full overflow-hidden rounded-2xl border border-rule bg-paper-card shadow-[0_12px_32px_-16px_rgba(38,38,36,0.3)]">
								{locSuggestions.map((suggestion) => (
									<li
										key={suggestion}
										className="cursor-pointer px-4 py-2.5 text-[13px] font-light text-ink-700 hover:bg-paper-alt"
										onClick={() => onLocationSelect(suggestion)}
									>
										{suggestion}
									</li>
								))}
							</ul>
						)}
					</div>
					<button
						type="button"
						onClick={onUseCurrentLocation}
						disabled={locationStatus === "loading"}
						className="text-xs font-light text-ink-500 underline underline-offset-4 decoration-rule hover:text-ink-900 focus:outline-none disabled:opacity-50"
					>
						{locationStatus === "loading"
							? "Locating…"
							: "Use current location"}
					</button>
					{locationStatus === "error" && locationError && (
						<p className="text-xs text-clay-600">{locationError}</p>
					)}
				</div>

				{/* Available time */}
				<div className="space-y-2">
					<p className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-500">Available time</p>
					<div className="flex flex-wrap gap-2">
						{timeOptions.map((opt) => (
							<ChoicePill
								key={opt}
								label={opt}
								selected={timeChoice === opt}
								onClick={() => setTimeChoice(opt)}
							/>
						))}
					</div>
				</div>

				{/* Mood */}
				<div className="space-y-2">
					<p className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-500">Mood / vibe</p>
					<div className="flex flex-wrap gap-2">
						{moodOptions.map((opt) => (
							<ChoicePill
								key={opt}
								label={opt}
								selected={moodChoice === opt}
								onClick={() => setMoodChoice(opt)}
							/>
						))}
					</div>
				</div>

				{/* Budget */}
				<div className="space-y-2">
					<p className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-500">Budget</p>
					<div className="flex flex-wrap gap-2">
						{budgetOptions.map((opt) => (
							<ChoicePill
								key={opt}
								label={opt}
								selected={budgetChoice === opt}
								onClick={() => setBudgetChoice(opt)}
							/>
						))}
					</div>
				</div>

				{/* Transport + Energy */}
				<div className="grid grid-cols-2 gap-4">
					<div className="space-y-2">
						<p className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-500">Transport</p>
						<div className="flex flex-wrap gap-2">
							{transportOptions.map((opt) => (
								<ChoicePill
									key={opt}
									label={opt}
									selected={transportChoice === opt}
									onClick={() => setTransportChoice(opt)}
								/>
							))}
						</div>
					</div>
					<div className="space-y-2">
						<p className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-500">Energy</p>
						<div className="flex flex-wrap gap-2">
							{energyOptions.map((opt) => (
								<ChoicePill
									key={opt}
									label={opt}
									selected={energyChoice === opt}
									onClick={() => setEnergyChoice(opt)}
								/>
							))}
						</div>
					</div>
				</div>

				{/* Companions */}
				<div className="space-y-2">
					<p className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-500">Who&apos;s coming?</p>
					<div className="flex flex-wrap gap-2">
						{companionsOptions.map((opt) => (
							<ChoicePill
								key={opt}
								label={opt}
								selected={companionsChoice === opt}
								onClick={() => setCompanionsChoice(opt)}
							/>
						))}
					</div>
				</div>
			</div>

			<button
				type="button"
				onClick={onGenerate}
				disabled={isGenerating}
				className="mt-8 w-full rounded-full bg-ink-900 py-3.5 text-sm font-medium text-white transition hover:bg-[#3a3a37] focus:outline-none focus-visible:ring-2 focus-visible:ring-ink-500/30 focus-visible:ring-offset-2 disabled:opacity-50"
			>
				{isGenerating ? "Generating…" : "Generate plans"}
			</button>
		</section>
	);
}
