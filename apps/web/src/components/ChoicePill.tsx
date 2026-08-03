"use client";

type ChoicePillProps = {
  label: string;
  selected: boolean;
  onClick: () => void;
};

export default function ChoicePill({ label, selected, onClick }: ChoicePillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`rounded-full border px-3.5 py-1.5 text-[13px] font-light transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ink-500/30 focus-visible:ring-offset-2 ${
        selected
          ? "border-ink-900 bg-ink-900 font-normal text-white"
          : "border-rule bg-transparent text-ink-700 hover:border-ink-500/50"
      }`}
    >
      {label}
    </button>
  );
}
