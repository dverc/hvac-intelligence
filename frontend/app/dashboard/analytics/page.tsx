import { CohortHeatmap } from "@/components/CohortHeatmap";
import { SavedByAIMetrics } from "@/components/SavedByAIMetrics";
import {
  defaultAnalyticsRange,
  getChurnCohorts,
  getSavedByAI,
} from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AnalyticsPage() {
  const { start, end } = defaultAnalyticsRange();
  const priorStart = new Date(start);
  priorStart.setDate(priorStart.getDate() - 90);

  const [cohorts, savedByAI, priorSavedByAI] = await Promise.all([
    getChurnCohorts(90, 10),
    getSavedByAI(start, end),
    getSavedByAI(priorStart.toISOString(), start),
  ]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Analytics</h1>
        <p className="text-sm text-gray-500 dark:text-slate-400">
          Cohort risk heatmap and full Saved-by-AI retention breakdown.
        </p>
      </header>

      <CohortHeatmap data={cohorts} />

      <SavedByAIMetrics
        data={savedByAI}
        priorSuccessRate={priorSavedByAI.intervention_success_rate}
      />
    </div>
  );
}
