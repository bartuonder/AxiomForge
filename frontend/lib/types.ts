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

export type ResearchSnapshot = {
  thread_id: string;
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
};

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
