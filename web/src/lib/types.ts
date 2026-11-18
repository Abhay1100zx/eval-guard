export interface Run {
  id: string;
  run_name: string;
  domain: string;
  timestamp: string;
  model_name: string | null;
  embedding_model: string | null;
  total_questions: number;
  avg_faithfulness: number;
  avg_relevance: number;
  avg_retrieval_hit_rate: number | null;
  avg_mrr: number | null;
  avg_safety: number | null;
  avg_latency_ms: number;
  total_cost: number;
  status: string;
  scorer: string | null;
  is_simulated: number;
  suite: string | null;
  prompt_name: string | null;
  prompt_hash: string | null;
  experiment_id: string | null;
  variant_label: string | null;
}

export interface Context {
  text: string;
  score: number;
  metadata?: { source?: string };
}

export interface QResult {
  id: string;
  question_id: string;
  kind: string | null;
  question: string;
  ground_truth: string;
  generated_answer: string;
  retrieved_contexts: Context[];
  faithfulness_score: number;
  faithfulness_reason: string;
  relevance_score: number;
  relevance_reason: string;
  hit_rate: number | null;
  mrr: number | null;
  safety_pass: number | null;
  safety_reason: string | null;
  latency_ms: number;
  cost: number;
}

export interface Domain {
  key: string;
  name: string;
  icon: string;
  description: string;
  faithfulness_threshold: number;
  relevance_threshold: number;
  safeguard_notice: string | null;
  sample_question: string;
}

export interface Status {
  version: string;
  llm_provider: string;
  answer_model: string;
  judge_model: string;
  is_mock: boolean;
  embedding_model: string;
  auth_disabled: boolean;
}

export interface DriftMetric {
  ks_statistic: number;
  p_value: number;
  baseline_mean: number;
  current_mean: number;
  mean_delta: number;
  severity: string;
  drift_detected: boolean;
  rolling_trend: string;
}

export interface DriftReport {
  overall_status: string;
  metrics: Record<string, DriftMetric>;
  recommendation: string;
}

export interface Job {
  id: string;
  kind: string;
  domains: string[];
  status: "queued" | "running" | "done" | "failed";
  progress: { domain: string | null; current: number; total: number; domains_done: number; domains_total: number };
  results: {
    domain: string;
    status: string;
    error?: string;
    run?: Run;
    drift_report?: DriftReport | null;
    drift_skipped_reason?: string | null;
    skipped?: { question_id: string; error: string }[];
  }[];
  error: string | null;
}

export interface PromptVersion {
  id: string;
  name: string;
  system_prompt: string;
  created_at: string;
  is_default: number;
}

export type QuestionKind = "standard" | "out_of_scope" | "injection" | "injection_hybrid";

export interface TestQuestion {
  id: string;
  domain: string;
  kind: QuestionKind;
  question: string;
  ground_truth: string;
  expected_keywords: string[];
  must_not_contain: string[];
  answerable: boolean;
  source: "builtin" | "custom";
}

export interface Experiment {
  id: string;
  name: string;
  kind: "prompt" | "model";
  domain: string;
  suite: string;
  question_limit: number | null;
  status: "queued" | "running" | "done" | "failed";
  variants: { label: string; prompt_name: string; model: string | null }[];
  created_at: string;
  error: string | null;
}

export interface ExperimentAnswer {
  generated_answer: string;
  faithfulness_score: number;
  relevance_score: number;
  hit_rate: number | null;
  safety_pass: number | null;
  safety_reason: string | null;
  latency_ms: number;
}

export interface ExperimentDetail {
  experiment: Experiment;
  runs: Run[];
  questions: { question_id: string; question: string; ground_truth: string; kind: string; answers: Record<string, ExperimentAnswer> }[];
}
