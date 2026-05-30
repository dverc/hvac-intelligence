import { ChurnRiskDonut } from "@/components/ChurnRiskDonut";
import { LiveCallFeed } from "@/components/LiveCallFeed";
import { SavedByAIMetrics } from "@/components/SavedByAIMetrics";
import {
  defaultAnalyticsRange,
  getChurnProbabilityDistribution,
  getSavedByAI,
} from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const { start, end } = defaultAnalyticsRange();

  const [distribution, savedByAI] = await Promise.all([
    getChurnProbabilityDistribution(),
    getSavedByAI(start, end),
  ]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Operations Overview</h1>
        <p className="text-sm text-gray-500 dark:text-slate-400">
          Portfolio churn risk, AI retention impact, and live call activity.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <ChurnRiskDonut data={distribution} />
        </div>
        <div className="xl:col-span-1">
          <LiveCallFeed />
        </div>
      </div>

      <SavedByAIMetrics data={savedByAI} />
    </div>
  );
}
