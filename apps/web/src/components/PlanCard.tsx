"use client";

import { useState } from "react";
import { Plan } from "@/lib/types";

type PlanCardProps = {
  plan: Plan;
};

const typeStyles: Record<
  Plan["type"],
  { badge: string; featured: boolean; border: string; bannerBg: string; bannerText: string; shadow: string }
> = {
  "Lowest Effort": {
    badge: "bg-sky-100 text-sky-700",
    featured: false,
    border: "border-sage-200",
    bannerBg: "",
    bannerText: "",
    shadow: "shadow-sm",
  },
  "Best Match": {
    badge: "bg-sage-200 text-sage-800",
    featured: true,
    border: "border-sage-300",
    bannerBg: "bg-sage-100",
    bannerText: "text-sage-700",
    shadow: "shadow-[0_2px_16px_rgba(47,74,52,0.12),0_1px_4px_rgba(0,0,0,0.04)]",
  },
  "More Fun": {
    badge: "bg-amber-100 text-amber-700",
    featured: false,
    border: "border-sage-200",
    bannerBg: "",
    bannerText: "",
    shadow: "shadow-sm",
  },
};

const categoryEmoji: Record<string, string> = {
  Cafe: "☕",
  Bookstore: "📚",
  Scenic: "🌿",
  Restaurant: "🍽️",
  Entertainment: "🎮",
  Dessert: "🍦",
};

export default function PlanCard({ plan }: PlanCardProps) {
  const [saved, setSaved] = useState(false);
  const styles = typeStyles[plan.type];

  return (
    <article
      className={`overflow-hidden rounded-3xl border bg-white transition ${styles.border} ${styles.shadow}`}
    >
      {styles.featured && (
        <div className={`px-5 py-2.5 text-center ${styles.bannerBg}`}>
          <p className={`text-[11px] font-semibold uppercase tracking-widest ${styles.bannerText}`}>
            ★ Our Recommendation
          </p>
        </div>
      )}

      <div className="p-5">
        <div className="flex items-center justify-between gap-3">
          <span
            className={`rounded-full px-3 py-1 text-xs font-semibold ${styles.badge}`}
          >
            {plan.type}
          </span>
          <span className="text-sm font-semibold text-stone-900">
            {plan.estimatedCost}
          </span>
        </div>

        <div className="mt-4">
          <h3 className="text-[17px] font-semibold leading-snug text-stone-950">
            {plan.title}
          </h3>
          <p className="mt-1.5 text-sm leading-relaxed text-stone-500">
            {plan.summary}
          </p>
        </div>

        <div className="mt-5 space-y-2">
          {plan.stops.map((stop) => (
            <div
              key={stop.name}
              className="flex items-center justify-between gap-3 rounded-2xl bg-sage-50 px-4 py-3"
            >
              <div className="flex min-w-0 items-center gap-2.5">
                <span className="shrink-0 text-base">
                  {categoryEmoji[stop.category] ?? "📍"}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-stone-900">
                    {stop.name}
                  </p>
                  <p className="text-xs text-stone-400">{stop.category}</p>
                </div>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-xs font-medium text-stone-700">
                  {stop.durationMinutes} min
                </p>
                <p className="text-xs text-stone-400">{stop.estimatedCost}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          <div className="rounded-2xl bg-sage-50 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-sage-500">
              Total time
            </p>
            <p className="mt-1 text-sm font-semibold text-stone-900">
              {plan.totalDurationMinutes} min
            </p>
          </div>
          <div className="rounded-2xl bg-sage-50 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-sage-500">
              Travel
            </p>
            <p className="mt-1 text-sm font-semibold text-stone-900">
              {plan.travelTimeMinutes} min
            </p>
          </div>
        </div>

        <div className="mt-4 rounded-2xl bg-sage-50 p-4">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-sage-500">
            Why it fits
          </p>
          <p className="mt-1.5 text-sm leading-relaxed text-stone-700">
            {plan.vibeMatchReason}
          </p>
        </div>

        <div className="mt-5 flex flex-col gap-2.5">
          <a
            href={plan.mapUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex w-full items-center justify-center rounded-full bg-sage-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-sage-800 active:scale-[0.98]"
          >
            Open map
          </a>
          <button
            type="button"
            onClick={() => setSaved(true)}
            className={`inline-flex w-full items-center justify-center rounded-full border px-4 py-3 text-sm font-semibold transition active:scale-[0.98] ${
              saved
                ? "border-sage-200 bg-sage-100 text-sage-600"
                : "border-sage-200 bg-white text-stone-900 hover:border-sage-300 hover:bg-sage-50"
            }`}
          >
            {saved ? "✓ Saved" : "Save for later"}
          </button>
        </div>
      </div>
    </article>
  );
}
