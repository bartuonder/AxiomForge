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

export type ResearchSnapshot = {
  thread_id: string;
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

export type CampaignStatus = "queued" | "running" | "completed" | "needs_review" | "failed";

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
