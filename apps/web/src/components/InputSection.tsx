"use client";

import ChoicePill from "@/components/ChoicePill";
import { LocationStatus } from "@/lib/useCurrentLocation";

type InputSectionProps = {
	location: string;
	onLocationChange: (value: string) => void;
	onLocationSelect: (value: string) => void;
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
	onUseCurrentLocation: () => void;
	locationStatus: LocationStatus;
	locationError: string | null;
	onGenerate: () => void;
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

export default function InputSection({
	location,
	onLocationChange,
	onLocationSelect,
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
	onGenerate,
}: InputSectionProps) {
	return (
		<section className="rounded-3xl border border-sage-200 bg-white/90 p-5 shadow-sm">
			<div className="space-y-5">
				{/* Location */}
				<div className="space-y-2">
					<p className="text-sm font-semibold text-stone-900">Where are you?</p>
					<div className="relative">
						<span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 select-none text-base">
							📍
						</span>
						<input
							value={location}
							onChange={(e) => onLocationChange(e.target.value)}
							className="w-full rounded-2xl border border-sage-200 bg-sage-50 py-3 pl-9 pr-4 text-sm text-stone-900 placeholder:text-stone-400 transition focus:border-sage-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-sage-100"
							placeholder="Enter your location"
						/>
						{locSuggestions && locSuggestions.length > 0 && (
							<ul className="absolute z-10 mt-1 w-full rounded-2xl border border-sage-200 bg-white shadow-sm">
								{locSuggestions.map((suggestion) => (
									<li
										key={suggestion}
										className="cursor-pointer px-4 py-2 text-sm text-stone-900 hover:bg-sage-100"
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
						className="text-xs font-medium text-sage-400 hover:text-sage-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-sage-400 disabled:opacity-50"
					>
						{locationStatus === "loading"
							? "Locating…"
							: "Use current location"}
					</button>
					{locationStatus === "error" && locationError && (
						<p className="text-xs text-red-500">{locationError}</p>
					)}
				</div>

				{/* Available time */}
				<div className="space-y-2">
					<p className="text-sm font-semibold text-stone-900">Available time</p>
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
					<p className="text-sm font-semibold text-stone-900">Mood / vibe</p>
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
					<p className="text-sm font-semibold text-stone-900">Budget</p>
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
						<p className="text-sm font-semibold text-stone-900">Transport</p>
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
						<p className="text-sm font-semibold text-stone-900">Energy</p>
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
			</div>

			<button
				type="button"
				onClick={onGenerate}
				className="mt-6 w-full rounded-full bg-sage-700 py-4 text-sm font-semibold text-white shadow-sm transition hover:bg-sage-800 active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-sage-400"
			>
				Generate plans
			</button>
		</section>
	);
}
