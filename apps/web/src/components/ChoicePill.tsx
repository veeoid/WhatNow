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
      className={`rounded-full px-4 py-2 text-sm font-medium transition-all active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-sage-300 ${
        selected
          ? "bg-sage-700 text-white shadow-sm"
          : "bg-sage-100 text-sage-700 hover:bg-sage-200"
      }`}
    >
      {label}
    </button>
  );
}
