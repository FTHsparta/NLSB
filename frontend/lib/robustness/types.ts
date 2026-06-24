/**
 * Mirrors `backend/app/robustness/robustness.py`'s `run_robustness` return
 * shape verbatim -- field names are kept snake_case exactly as the backend
 * serializes them (no camelCase remapping) so there is no translation layer
 * that could silently drift from the real schema. This file describes the
 * contract; it computes nothing.
 */

export type Verdict = "PASS" | "SHAKY" | "LIKELY_OVERFIT" | "UNTESTABLE";

export interface BacktestMetrics {
  total_return: number;
  annualized_return: number;
  sharpe_ratio: number | null;
  max_drawdown: number;
  win_rate: number | null;
  num_trades: number;
  start: string;
  end: string;
}

export interface FoldResult {
  fold_index: number;
  is_start: string;
  is_end: string;
  oos_start: string;
  oos_end: string;
  chosen_params: Record<string, number>;
  is_sharpe: number | null;
  is_total_return: number | null;
  is_num_trades: number;
  oos_sharpe: number | null;
  oos_total_return: number | null;
  oos_num_trades: number;
  low_confidence: boolean;
  error: string | null;
}

export interface WalkForwardResult {
  folds: FoldResult[];
  aggregate_is_sharpe: number | null;
  aggregate_oos_sharpe: number | null;
  degradation: number | null;
}

export interface GridPointResult {
  value: number;
  sharpe_ratio: number | null;
  per_period_sharpe_ratio: number | null;
  total_return: number | null;
  num_trades: number;
  error: string | null;
}

export interface ParamSensitivity {
  param_id: string;
  kind: "period" | "threshold";
  stated_value: number;
  grid_points: GridPointResult[];
  peakiness: number | null;
  robustness_label: string;
}

export interface RegimeBreakdown {
  regime: string;
  share_of_time: number;
  total_return: number | null;
  sharpe_ratio: number | null;
  num_entries: number;
  num_bars: number;
}

export interface MarginalConcentration {
  axis: "trend" | "volatility";
  dominant_label: string;
  share: number;
}

export interface RegimeReport {
  breakdowns: RegimeBreakdown[];
  concentrated_regime: string | null;
  concentration_share: number | null;
  marginal_flags: MarginalConcentration[];
}

export interface DeflatedSharpeResult {
  n_trials: number;
  var_sr_trials: number;
  sr0: number;
  dsr: number | null;
}

export interface VerdictResult {
  verdict: Verdict;
  reasons: string[];
  details: Record<string, unknown>;
}

export interface NoExitResult {
  message: string;
  first_entry_date: string | null;
  strategy_metrics: BacktestMetrics | null;
  benchmark_metrics: BacktestMetrics | null;
}

/** The exact dict `run_robustness` returns, kind-discriminated. */
export type RobustnessResult =
  | {
      kind: "no_exit";
      no_exit: NoExitResult;
      sensitivity: null;
      walk_forward: null;
      deflated_sharpe: null;
      regime: null;
      verdict: null;
    }
  | {
      kind: "full";
      no_exit: null;
      sensitivity: ParamSensitivity[];
      walk_forward: WalkForwardResult;
      deflated_sharpe: DeflatedSharpeResult;
      regime: RegimeReport;
      verdict: VerdictResult;
    };
