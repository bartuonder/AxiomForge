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

export const STEP_LABELS: Record<string, string> = {
  literature_node: "Literature",
  planner_node: "Planner",
  experiment_node: "Experiment",
  verifier_node: "Verifier",
  report_node: "Report",
  consistency_checker_node: "Claims",
};

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
