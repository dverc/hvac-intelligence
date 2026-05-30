import type { RiskTier } from "@/types/churn";
import { RISK_COLORS } from "@/types/churn";

interface Props {
  tier: RiskTier | string;
  className?: string;
}

export function RiskBadge({ tier, className = "" }: Props) {
  const normalized = (tier?.toUpperCase() ?? "LOW") as RiskTier;
  const color = RISK_COLORS[normalized] ?? RISK_COLORS.LOW;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold text-white ${className}`}
      style={{ backgroundColor: color }}
    >
      {normalized}
    </span>
  );
}
