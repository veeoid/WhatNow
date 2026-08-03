"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import InputSection from "@/components/InputSection";
import PlanCard from "@/components/PlanCard";
import { Plan } from "@/lib/types";
import { useCurrentLocation } from "@/lib/useCurrentLocation";
import { getGeocode, getReverseGeocode } from "@/lib/geoapify";

export default function Home() {
	const [location, setLocation] = useState("");
	const [locSuggestions, setLocSuggestions] = useState<string[]>([]);
	const skipNextFetchRef = useRef(false);
	const [timeChoice, setTimeChoice] = useState("3 hours");
	const [moodChoice, setMoodChoice] = useState("Chill");
	const [budgetChoice, setBudgetChoice] = useState("Cheap");
	const [transportChoice, setTransportChoice] = useState("Walk");
	const [energyChoice, setEnergyChoice] = useState("Medium");
	const [companionsChoice, setCompanionsChoice] = useState("Solo");
	const [plans, setPlans] = useState<Plan[]>([]);
	const [planStartTime, setPlanStartTime] = useState<Date | null>(null);
	const [isGenerating, setIsGenerating] = useState(false);
	const [generationError, setGenerationError] = useState<string | null>(null);
	const resultsRef = useRef<HTMLElement>(null);

	const geo = useCurrentLocation();

	const handleUseCurrentLocation = () => {
		geo.request((coords) => {
			skipNextFetchRef.current = true;
			getReverseGeocode(coords.lat, coords.lng)
				.then((data) => {
					setLocation(
						data.results?.[0]?.formatted ??
							`Near you (${coords.lat.toFixed(2)}, ${coords.lng.toFixed(2)})`,
					);
					setLocSuggestions([]);
				})
				.catch((error) => {
					console.error(error);
					setLocation(
						`Near you (${coords.lat.toFixed(2)}, ${coords.lng.toFixed(2)})`,
					);
					setLocSuggestions([]);
				});
		});
	};

	useEffect(() => {
		if (plans.length > 0 && window.innerWidth < 1024) {
			resultsRef.current?.scrollIntoView({
				behavior: "smooth",
				block: "start",
			});
		}
	}, [plans]);

	useEffect(() => {
		if (skipNextFetchRef.current) {
			skipNextFetchRef.current = false;
			return;
		}
		if (!location) {
			return;
		}
		const controller = new AbortController();
		const timeoutId = setTimeout(() => {
			getGeocode(location, controller.signal)
				.then((data) => {
					setLocSuggestions(
						data.results?.map((result) => result.formatted) ?? [],
					);
				})
				.catch((error) => {
					if (error instanceof Error && error.name !== "AbortError") {
						console.error(error);
						setLocSuggestions([]);
					}
				});
		}, 300);
		return () => {
			clearTimeout(timeoutId);
			controller.abort();
		};
	}, [location]);

	const handleLocationChange = (value: string) => {
		setLocation(value);
		if (!value) {
			setLocSuggestions([]);
		}
	};

	const handleLocationSelect = (value: string) => {
		skipNextFetchRef.current = true;
		setLocation(value);
		setLocSuggestions([]);
	};

	const handleDismissSuggestions = useCallback(() => {
		skipNextFetchRef.current = true;
		setLocSuggestions([]);
	}, []);

	const handleGenerate = async () => {
		setIsGenerating(true);
		setGenerationError(null);
		try {
			const response = await fetch("/api/plan", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					location,
					timeChoice,
					moodChoice,
					budgetChoice,
					transportChoice,
					energyChoice,
					companionsChoice,
				}),
			});
			const data = await response.json();
			if (!response.ok) {
				throw new Error(data.error ?? "Something went wrong generating plans.");
			}
			setPlans(data.plans);
			setPlanStartTime(new Date());
		} catch (error) {
			setGenerationError(
				error instanceof Error
					? error.message
					: "Something went wrong generating plans.",
			);
		} finally {
			setIsGenerating(false);
		}
	};

	return (
		<div className="min-h-screen bg-gradient-to-b from-sage-50 to-sage-100">
			<main className="mx-auto max-w-6xl px-4 py-10 sm:px-6 lg:px-8">
				<div className="mx-auto max-w-2xl">
					<div className="space-y-6">
						<header className="text-center">
							<span className="inline-flex rounded-full bg-sage-200 px-3 py-1 text-[11px] font-semibold uppercase tracking-widest text-sage-700">
								Beta · Built for spontaneous plans
							</span>
							<h1 className="mt-5 text-5xl font-bold tracking-tight text-sage-950">
								WhatNow
							</h1>
							<p className="mt-3 text-xl font-semibold leading-snug text-stone-800">
								Find something worth doing right now.
							</p>
							<p className="mx-auto mt-2.5 max-w-[420px] text-sm leading-relaxed text-stone-500">
								Tell us your time, mood, and budget. We&apos;ll build five
								ready-to-go itineraries from real places near you.
							</p>
						</header>

						<InputSection
							location={location}
							onLocationChange={handleLocationChange}
							onLocationSelect={handleLocationSelect}
							onDismissSuggestions={handleDismissSuggestions}
							onUseCurrentLocation={handleUseCurrentLocation}
							locationStatus={geo.status}
							locationError={geo.error}
							locSuggestions={locSuggestions}
							timeChoice={timeChoice}
							setTimeChoice={setTimeChoice}
							moodChoice={moodChoice}
							setMoodChoice={setMoodChoice}
							budgetChoice={budgetChoice}
							setBudgetChoice={setBudgetChoice}
							transportChoice={transportChoice}
							setTransportChoice={setTransportChoice}
							energyChoice={energyChoice}
							setEnergyChoice={setEnergyChoice}
							companionsChoice={companionsChoice}
							setCompanionsChoice={setCompanionsChoice}
							onGenerate={handleGenerate}
							isGenerating={isGenerating}
						/>
					</div>
				</div>

				{/* Results, loading, error, or empty state */}
				{isGenerating ? (
					<div className="mt-10 flex items-center justify-center rounded-3xl border border-dashed border-sage-300 bg-white/50 px-6 py-20 text-center">
						<div>
							<p className="animate-pulse text-3xl">✦</p>
							<p className="mt-3 text-sm font-semibold text-stone-700">
								Finding real places nearby…
							</p>
							<p className="mt-2 text-sm leading-relaxed text-stone-400">
								This can take up to a minute while we search and build your
								itineraries.
							</p>
						</div>
					</div>
				) : generationError ? (
					<div className="mt-10 flex items-center justify-center rounded-3xl border border-dashed border-red-300 bg-white/50 px-6 py-20 text-center">
						<div>
							<p className="text-3xl">⚠</p>
							<p className="mt-3 text-sm font-semibold text-stone-700">
								Couldn&apos;t generate plans
							</p>
							<p className="mt-2 text-sm leading-relaxed text-stone-400">
								{generationError}
							</p>
						</div>
					</div>
				) : plans.length > 0 && planStartTime ? (
					<section ref={resultsRef} className="mt-10 scroll-mt-6">
						<div className="mb-4 text-center">
							<p className="text-base font-semibold text-stone-900">
								{plans.length} itineraries for the next {timeChoice.toLowerCase()}
							</p>
							<p className="mt-1 text-sm text-stone-500">
								{moodChoice} · {budgetChoice} · {transportChoice} ·{" "}
								{companionsChoice}
							</p>
						</div>
						<div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
							{plans.map((plan, index) => (
								<PlanCard
									key={`${plan.title}-${index}`}
									plan={plan}
									startTime={planStartTime}
								/>
							))}
						</div>
					</section>
				) : (
					<div className="mt-10 flex items-center justify-center rounded-3xl border border-dashed border-sage-300 bg-white/50 px-6 py-20 text-center">
						<div>
							<p className="text-3xl">✦</p>
							<p className="mt-3 text-sm font-semibold text-stone-700">
								Ready when you are
							</p>
							<p className="mt-2 text-sm leading-relaxed text-stone-400">
								Fill in your details and tap Generate plans to see five
								itineraries for your next few hours.
							</p>
						</div>
					</div>
				)}

				<footer className="mt-12 text-center text-xs text-sage-500">
					Plans for spontaneous moments
				</footer>
			</main>
		</div>
	);
}
