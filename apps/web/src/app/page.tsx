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

	// Wake the backend while the user fills in the form, so a cold start doesn't land on
	// their first "Generate plans" click. Fire-and-forget: failure here changes nothing.
	useEffect(() => {
		const controller = new AbortController();
		fetch("/api/warmup", { signal: controller.signal }).catch(() => {});
		return () => controller.abort();
	}, []);

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
		<div className="min-h-screen bg-paper">
			{/* Hero: full-bleed image, wordmark top-left, headline bottom-left */}
			<header className="hero-bg relative flex h-[78vh] min-h-[520px] flex-col justify-between px-6 py-7 sm:px-10 sm:py-9">
				<div className="flex items-center gap-2.5">
					<span className="h-5 w-5 rounded-full border border-white/70" />
					<span className="text-[15px] font-medium tracking-wide text-white">
						WhatNow
					</span>
				</div>

				<div className="max-w-2xl">
					<h1 className="text-[clamp(2.75rem,7vw,4.25rem)] font-light leading-[1.04] tracking-tight text-white">
						Something worth doing,
						<br />
						starting now
					</h1>
					<p className="mt-5 max-w-md text-[15px] font-light leading-relaxed text-white/70">
						Five itineraries built from real places near you — scheduled,
						costed, and ready to walk out the door.
					</p>
					<a
						href="#plan"
						className="mt-8 inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-medium text-ink-900 transition hover:bg-white/90"
					>
						Plan my next few hours
						<span aria-hidden="true">&rarr;</span>
					</a>
				</div>
			</header>

			<main id="plan" className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24 lg:px-8">
				<div className="mx-auto max-w-2xl">
					<div className="space-y-8">
						<div className="text-center">
							<p className="font-mono text-[10px] uppercase tracking-[0.22em] text-ink-500">
								Tell us the basics
							</p>
							<h2 className="mt-3 text-[30px] font-light tracking-tight text-ink-900">
								Where are you, and how long have you got?
							</h2>
							<p className="mx-auto mt-3 max-w-md text-sm font-light leading-relaxed text-ink-500">
								Everything below shapes what we look for nearby.
							</p>
						</div>

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
					<div className="mx-auto mt-24 max-w-md text-center">
						<p className="animate-pulse font-mono text-[10px] uppercase tracking-[0.2em] text-ink-500">
							Searching nearby
						</p>
						<p className="mt-3 text-[30px] font-light tracking-tight text-ink-900">
							Finding real places near you
						</p>
						<p className="mx-auto mt-3 max-w-md text-sm font-light leading-relaxed text-ink-500">
							Checking what&apos;s around, then building itineraries that fit the
							time you have. Usually about fifteen seconds.
						</p>
					</div>
				) : generationError ? (
					<div className="mx-auto mt-24 max-w-md text-center">
						<p className="font-mono text-[10px] uppercase tracking-[0.2em] text-clay-600">
							Something went wrong
						</p>
						<p className="mt-3 text-[30px] font-light tracking-tight text-ink-900">
							Couldn&apos;t build your plans
						</p>
						<p className="mx-auto mt-3 max-w-md text-sm font-light leading-relaxed text-ink-500">
							{generationError}
						</p>
					</div>
				) : plans.length > 0 && planStartTime ? (
					<section ref={resultsRef} className="mt-24 scroll-mt-8">
						<div className="mb-10 text-center">
							<p className="font-mono text-[10px] uppercase tracking-[0.22em] text-ink-500">
								{moodChoice} · {budgetChoice} · {transportChoice} ·{" "}
								{companionsChoice}
							</p>
							<h2 className="mt-3 text-[30px] font-light tracking-tight text-ink-900">
								{plans.length} ways to spend the next{" "}
								{timeChoice.toLowerCase()}
							</h2>
							<p className="mx-auto mt-3 max-w-md text-sm font-light leading-relaxed text-ink-500">
								Every stop is a real, nearby place — pick one and go.
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
					<div className="mx-auto mt-24 max-w-md text-center">
						<p className="text-sm font-light leading-relaxed text-ink-500">
							Fill in where you are and how long you&apos;ve got — five
							itineraries, built from places that actually exist near you.
						</p>
					</div>
				)}

			</main>

			<footer className="bg-[#262624] px-6 py-14 sm:px-10">
				<div className="mx-auto flex max-w-6xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
					<div className="flex items-center gap-2.5">
						<span className="h-4 w-4 rounded-full border border-white/50" />
						<span className="text-sm font-medium tracking-wide text-white">
							WhatNow
						</span>
					</div>
					<p className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/40">
						Real places · Real times · No filler
					</p>
				</div>
			</footer>
		</div>
	);
}
