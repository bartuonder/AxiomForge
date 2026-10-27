export type StepPhase = "pending" | "active" | "done";

export type ResearchStep = {
  id: string;
  phase: StepPhase;
};

export type FlaggedMetric = {
  model: string;
  metric: string;
  std: number;
};

export type Instability = {
  unstable: boolean;
  std_threshold: number;
  flagged: FlaggedMetric[];
};

export type ExperimentSpec = {
  statement: string;
  models: string[];
  dataset: string;
  params: Record<string, Record<string, string | number | null>>;
};

export type ResearchMode = "experiment" | "campaign";

export type CampaignClaim = {
  id: string;
  statement: string;
  metrics: string[];
  subject: string[];
  other: string[];
  quote?: string;
};

export type CampaignPlanSpec = {
  title: string;
  models: string[];
  datasets: string[];
  claims: CampaignClaim[];
  source?: { title?: string; citation?: string; url?: string; deviations?: string[] };
  tuning?: { iterations?: number; folds?: number };
};

export type CampaignEstimate = {
  datasets: number;
  model_runs: number;
  sandboxes: number;
  max_sandboxes: number;
  estimated_seconds: number;
  worst_case_seconds: number;
};

export type CampaignEvidence = {
  claim: string;
  quote: string;
  source: string;
};

export type CampaignCandidate = {
  spec: CampaignPlanSpec;
  estimate: CampaignEstimate;
  evidence: CampaignEvidence[];
  repeats?: string[];
};

export type ErrorInfo = {
  code: string;
  title: string;
  message: string;
  hint: string;
  technical: string;
};

export type ResearchSnapshot = {
  thread_id: string;
  error_info?: ErrorInfo | null;
  mode?: ResearchMode;
  campaign_specs?: CampaignCandidate[];
  selected_campaign?: number;
  campaign_id?: string;
  campaign_status?: string;
  campaign_mlflow_run_id?: string;
  status: "starting" | "running" | "paused" | "rejected" | "completed" | "needs_review" | "failed";
  next: string[];
  active_step: string;
  hypotheses: string[];
  experiment_specs: ExperimentSpec[];
  selected_hypothesis: number;
  approval_status: string;
  verification_status: string;
  verifier_feedback: string;
  instability: Instability;
  research_status: string;
  consistency_feedback: string;
  referee_notes: string[];
  error: string;
  steps: ResearchStep[];
};

export type CampaignStatus = "queued" | "running" | "completed" | "needs_review" | "failed" | "cancelled";

export type CampaignVerdict = {
  id: string;
  verdict: string;
  statement?: string;
};

export type CampaignSummary = {
  id: string;
  title: string;
  status: CampaignStatus;
  updated: string;
  origin?: string;
  statement?: string;
  datasets: number;
  finished: number;
  failed: number;
  verdicts: CampaignVerdict[];
};

export type CampaignDatasetState = {
  status: "queued" | "running" | "finished" | "failed";
  attempts?: number;
  seconds?: number;
  error?: string;
};

export type CampaignState = {
  id: string;
  title: string;
  status: CampaignStatus;
  updated: string;
  datasets: Record<string, CampaignDatasetState>;
  verdicts?: CampaignVerdict[];
  issues?: string[];
  error?: string;
  mlflow_run_id?: string;
};

export type SummaryVerdict = { code: string; label: string; tone: string; meaning: string };

export type SummaryConfidence = { level: "high" | "medium" | "low"; label: string; reason: string };

export type SummaryMetric = {
  metric: string;
  label: string;
  meaning: string;
  wins: number;
  losses: number;
  ties: number;
  total: number;
  median_difference: number;
  significant: boolean;
  testable: boolean;
};

export type SummaryChart = {
  metric: string;
  metric_label: string;
  subject_label: string;
  other_label: string;
  points: { dataset: string; label: string; subject: number; other: number }[];
};

export type SummaryClaim = {
  id: string;
  statement: string;
  verdict: SummaryVerdict;
  headline: string;
  confidence: SummaryConfidence;
  primary_metric: string;
  datasets_for: number;
  datasets_against: number;
  datasets_total: number;
  metrics: SummaryMetric[];
  chart: SummaryChart;
};

export type PlainSummary = {
  language: string;
  campaign_id: string;
  title: string;
  source: { title: string; citation: string } | null;
  status: { code: CampaignStatus; label: string; tone: string };
  progress: { finished: number; failed: number; total: number; percent: number };
  live: { running: { key: string; label: string }[]; eta_seconds: number | null; cancel_requested: boolean };
  actions: { cancel: boolean; retry: boolean };
  recoveries: number;
  headline: string;
  verdict_counts: Record<string, number>;
  claims: SummaryClaim[];
  ranking: { model: string; label: string; average_rank: number; position: number }[];
  method: string[];
  cautions: string[];
  datasets: { key: string; label: string }[];
  glossary: Record<string, { term: string; explanation: string }>;
  error: string | null;
  error_info: ErrorInfo | null;
};

export type LedgerEntry = {
  id: string;
  kind: string;
  key: string;
  [field: string]: unknown;
};

export type CampaignReport = {
  markdown: string;
  ledger: LedgerEntry[];
};

export const STEP_LABELS: Record<string, string> = {
  literature_node: "Literature",
  planner_node: "Planner",
  experiment_node: "Experiment",
  verifier_node: "Verifier",
  report_node: "Report",
  consistency_checker_node: "Claims",
  campaign_planner_node: "Campaign plan",
  campaign_node: "Campaign",
  meta_report_node: "Meta report",
  meta_consistency_node: "Claims",
};

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
