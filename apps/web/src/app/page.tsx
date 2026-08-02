"use client";

import { useEffect, useRef, useState } from "react";
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
			<main className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
				<div className="lg:grid lg:grid-cols-2 lg:gap-10 lg:items-start">
					{/* Left column: Hero + Form */}
					<div className="space-y-6 lg:sticky lg:top-8">
						<header className="text-center lg:text-left">
							<span className="inline-flex rounded-full bg-sage-200 px-3 py-1 text-[11px] font-semibold uppercase tracking-widest text-sage-700">
								Beta · Built for spontaneous plans
							</span>
							<h1 className="mt-5 text-5xl font-bold tracking-tight text-sage-950">
								WhatNow
							</h1>
							<p className="mt-3 text-xl font-semibold leading-snug text-stone-800">
								Find something worth doing right now.
							</p>
							<p className="mx-auto mt-2.5 max-w-[340px] text-sm leading-relaxed text-stone-500 lg:mx-0 lg:max-w-none">
								Pick your mood, time, budget, and transport. We&apos;ll suggest
								three realistic plans for the next few hours.
							</p>
						</header>

						<InputSection
							location={location}
							onLocationChange={handleLocationChange}
							onLocationSelect={handleLocationSelect}
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

					{/* Right column: Results, loading, error, or empty state */}
					{isGenerating ? (
						<div className="mt-8 flex items-center justify-center rounded-3xl border border-dashed border-sage-300 bg-white/50 px-6 py-20 text-center lg:mt-0">
							<div>
								<p className="text-3xl animate-pulse">✦</p>
								<p className="mt-3 text-sm font-semibold text-stone-700">
									Finding real places nearby…
								</p>
								<p className="mt-2 text-sm leading-relaxed text-stone-400">
									This can take up to a minute while we search and put
									together your plans.
								</p>
							</div>
						</div>
					) : generationError ? (
						<div className="mt-8 flex items-center justify-center rounded-3xl border border-dashed border-red-300 bg-white/50 px-6 py-20 text-center lg:mt-0">
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
					) : plans.length > 0 ? (
						<section
							ref={resultsRef}
							className="mt-8 scroll-mt-6 space-y-4 lg:mt-0"
						>
							<div className="px-1">
								<p className="text-base font-semibold text-stone-900">
									Here are three plans for your vibe
								</p>
								<p className="mt-1 text-sm text-stone-500">
									{moodChoice} · {timeChoice} · {budgetChoice} ·{" "}
									{transportChoice}
								</p>
							</div>
							{plans.map((plan) => (
								<PlanCard key={plan.type} plan={plan} />
							))}
						</section>
					) : (
						<div className="mt-8 flex items-center justify-center rounded-3xl border border-dashed border-sage-300 bg-white/50 px-6 py-20 text-center lg:mt-0">
							<div>
								<p className="text-3xl">✦</p>
								<p className="mt-3 text-sm font-semibold text-stone-700">
									Ready when you are
								</p>
								<p className="mt-2 text-sm leading-relaxed text-stone-400">
									Fill in your details and tap Generate plans to see three ideas
									for your next few hours.
								</p>
							</div>
						</div>
					)}
				</div>

				<footer className="mt-12 text-center text-xs text-sage-500">
					Plans for spontaneous moments
				</footer>
			</main>
		</div>
	);
}
