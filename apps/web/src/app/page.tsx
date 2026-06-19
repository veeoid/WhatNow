"use client";

import { useEffect, useRef, useState } from "react";
import InputSection from "@/components/InputSection";
import PlanCard from "@/components/PlanCard";
import { mockPlans } from "@/lib/mockPlans";
import { useCurrentLocation } from "@/lib/useCurrentLocation";

export default function Home() {
	const [location, setLocation] = useState("");
	const [timeChoice, setTimeChoice] = useState("3 hours");
	const [moodChoice, setMoodChoice] = useState("Chill");
	const [budgetChoice, setBudgetChoice] = useState("Cheap");
	const [transportChoice, setTransportChoice] = useState("Walk");
	const [energyChoice, setEnergyChoice] = useState("Medium");
	const [showResults, setShowResults] = useState(false);
	const resultsRef = useRef<HTMLElement>(null);

	const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(
		null,
	);

	const geo = useCurrentLocation();

	// When the hook gets coordinates, reflect them in the UI + store them.
	useEffect(() => {
		if (geo.status === "success" && geo.coords) {
			setCoords(geo.coords);
			setLocation(
				`Near you (${geo.coords.lat.toFixed(2)}, ${geo.coords.lng.toFixed(2)})`,
			);
		}
	}, [geo.status, geo.coords]);

	useEffect(() => {
		if (showResults && window.innerWidth < 1024) {
			resultsRef.current?.scrollIntoView({
				behavior: "smooth",
				block: "start",
			});
		}
	}, [showResults]);

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
							onLocationChange={setLocation}
							onUseCurrentLocation={geo.request}
							locationStatus={geo.status}
							locationError={geo.error}
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
							onGenerate={() => setShowResults(true)}
						/>
					</div>

					{/* Right column: Results or empty state */}
					{showResults ? (
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
							{mockPlans.map((plan) => (
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
					Plans for spontaneous moments · No backend yet
				</footer>
			</main>
		</div>
	);
}
