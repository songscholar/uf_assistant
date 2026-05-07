"""
UF Stock Assistant — Experiment Runner Service

Orchestrates market regime detection, batch backtests, scoring, and evolution.
Adapted from QuantDinger: uses UF's BacktestService, LlmService, and strategy_service.
"""

from __future__ import annotations

import copy
import time
from datetime import datetime
from typing import Any

from app.core.logging import get_logger
from app.core.llm_adapter import LlmService
from app.strategies.backtest import BacktestService
from app.strategies.experiment.evolution import StrategyEvolutionService
from app.strategies.experiment.prompts import (
    SYSTEM_PROMPT,
    build_round_prompt,
    extract_indicator_params,
    parse_llm_candidates,
)
from app.strategies.experiment.regime import MarketRegimeService
from app.strategies.experiment.scoring import StrategyScoringService

logger = get_logger("app.strategies.experiment.runner")

DEFAULT_MAX_ROUNDS = 3
DEFAULT_CANDIDATES_PER_ROUND = 5
EARLY_STOP_SCORE = 82.0


class ExperimentRunnerService:
    """Orchestrate market regime detection, batch backtests, scoring, and evolution."""

    def __init__(
        self,
        *,
        backtest_service: BacktestService | None = None,
        regime_service: MarketRegimeService | None = None,
        scoring_service: StrategyScoringService | None = None,
        evolution_service: StrategyEvolutionService | None = None,
    ):
        self.backtest_service = backtest_service or BacktestService()
        self.regime_service = regime_service or MarketRegimeService()
        self.scoring_service = scoring_service or StrategyScoringService()
        self.evolution_service = evolution_service or StrategyEvolutionService()

    # ── LLM-driven multi-round AI pipeline ────────────────────────────────

    def run_ai_pipeline(
        self,
        payload: dict[str, Any],
        on_progress: Any | None = None,
    ) -> dict[str, Any]:
        """
        Multi-round LLM-driven optimization pipeline.

        Flow per round:
          1. Build prompt from indicator code + regime + previous results
          2. LLM proposes N candidate parameter sets
          3. Batch-backtest each candidate
          4. Score & rank
          5. If best score >= threshold or max rounds reached -> stop

        Args:
            payload: Request body (base config + optional overrides).
            on_progress: Optional callback invoked after each round.

        Returns:
            Full experiment result dict.
        """
        base = payload.get("base") or payload
        max_rounds = int(payload.get("maxRounds") or DEFAULT_MAX_ROUNDS)
        n_per_round = int(payload.get("candidatesPerRound") or DEFAULT_CANDIDATES_PER_ROUND)
        early_stop = float(payload.get("earlyStopScore") or EARLY_STOP_SCORE)

        snapshot, start_date, end_date = self._build_snapshot(base)
        indicator_code = snapshot.get("code") or ""
        indicator_params = extract_indicator_params(indicator_code)

        # Step 1: detect market regime
        self._emit(on_progress, "regime", {"status": "running"})
        try:
            regime = self._detect_regime(base)
        except Exception as exc:
            logger.warning("regime_detection_failed", error=str(exc))
            regime = None
        self._emit(on_progress, "regime", {"status": "done", "regime": regime})

        # Step 2..N: multi-round LLM optimization
        llm = LlmService.from_env()

        all_rounds: list[dict[str, Any]] = []
        global_best: dict[str, Any] | None = None
        global_best_score = -1.0
        previous_results: list[dict[str, Any]] | None = None

        for round_num in range(1, max_rounds + 1):
            round_start = time.time()
            self._emit(on_progress, "round_start", {
                "round": round_num,
                "maxRounds": max_rounds,
                "status": "running",
            })

            # Build prompt
            prompt = build_round_prompt(
                indicator_code=indicator_code,
                indicator_params=indicator_params,
                regime=regime,
                previous_results=previous_results,
                round_number=round_num,
                n_candidates=n_per_round,
            )

            # Call LLM
            try:
                response = llm.chat(
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7 + round_num * 0.05,
                )
                raw_text = response.get("content", "")
                candidates_raw = parse_llm_candidates(raw_text)
            except Exception as exc:
                logger.error("llm_call_failed", round=round_num, error=str(exc))
                candidates_raw = []

            if not candidates_raw:
                logger.warning("round_no_candidates", round=round_num)
                all_rounds.append({
                    "round": round_num,
                    "candidates": [],
                    "bestScore": global_best_score,
                    "error": "LLM returned no valid candidates",
                })
                continue

            # Backtest each candidate
            round_ranked: list[dict[str, Any]] = []
            n_cand = len(candidates_raw)
            for idx, cand in enumerate(candidates_raw, start=1):
                self._emit(on_progress, "candidate_backtest", {
                    "round": round_num,
                    "index": idx,
                    "total": n_cand,
                })
                cand_snapshot = self._apply_candidate_to_snapshot(
                    snapshot, cand, indicator_params,
                )
                try:
                    result = self._run_backtest(cand_snapshot, start_date, end_date)
                except Exception as exc:
                    logger.error("backtest_failed", name=cand.get("name"), error=str(exc))
                    result = {}

                score = self.scoring_service.score_result(result, regime=regime)
                round_ranked.append({
                    "name": cand.get("name", f"R{round_num}_{idx}"),
                    "reasoning": cand.get("reasoning", ""),
                    "source": f"ai_round_{round_num}",
                    "overrides": {
                        "indicatorParams": cand.get("indicatorParams", {}),
                        "riskParams": cand.get("riskParams", {}),
                    },
                    "snapshot": cand_snapshot,
                    "score": score,
                    "result": self._slim_result(result),
                })

            round_ranked = self.scoring_service.rank_results(round_ranked)
            round_best = round_ranked[0] if round_ranked else None
            round_best_score = float(
                (round_best or {}).get("score", {}).get("overallScore", 0)
            )

            if round_best and round_best_score > global_best_score:
                global_best = round_best
                global_best_score = round_best_score

            round_info = {
                "round": round_num,
                "candidates": round_ranked,
                "bestScore": round_best_score,
                "globalBestScore": global_best_score,
                "elapsed": round(time.time() - round_start, 1),
            }
            all_rounds.append(round_info)
            self._emit(on_progress, "round_done", round_info)

            previous_results = round_ranked

            if global_best_score >= early_stop:
                logger.info(
                    "early_stop", score=global_best_score, threshold=early_stop, round=round_num
                )
                break

        # Final output
        all_candidates: list[dict[str, Any]] = []
        for rd in all_rounds:
            all_candidates.extend(rd.get("candidates") or [])
        all_candidates = self.scoring_service.rank_results(all_candidates)

        return {
            "regime": regime,
            "generatorHints": self._build_generator_hints(regime) if regime else {},
            "indicatorParams": indicator_params,
            "rounds": [
                {
                    "round": r["round"],
                    "bestScore": r.get("bestScore", 0),
                    "globalBestScore": r.get("globalBestScore", 0),
                    "candidateCount": len(r.get("candidates") or []),
                    "elapsed": r.get("elapsed", 0),
                    "error": r.get("error"),
                }
                for r in all_rounds
            ],
            "rankedStrategies": all_candidates[:20],
            "bestStrategyOutput": self._build_best_output(global_best),
            "experiment": {
                "totalRounds": len(all_rounds),
                "totalCandidates": len(all_candidates),
                "globalBestScore": global_best_score,
            },
        }

    # ── Structured tune (grid/random, no LLM) ────────────────────────────

    def run_structured_tune(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Grid or random search over parameterSpace. No LLM involved.

        Args:
            payload: Request body with base, parameterSpace, evolution config.

        Returns:
            Experiment result with ranked strategies.
        """
        base = payload.get("base") or payload
        parameter_space = payload.get("parameterSpace") or {}
        if not isinstance(parameter_space, dict) or not parameter_space:
            raise ValueError("parameterSpace is required and must be a non-empty object")

        evolution = payload.get("evolution") or {}
        max_variants = int(evolution.get("maxVariants") or 48)
        method = str(evolution.get("method") or "grid").lower()
        if method not in ("grid", "random"):
            method = "grid"
        include_baseline = payload.get("includeBaseline", True)

        t0 = time.time()
        snapshot, start_date, end_date = self._build_snapshot(base)
        try:
            regime = self._detect_regime(base)
        except Exception:
            regime = None

        candidates = self._build_candidates(
            base_snapshot=snapshot,
            variants=payload.get("variants") or [],
            parameter_space=parameter_space,
            evolution={
                "method": method,
                "maxVariants": max_variants,
                "parameterSpace": parameter_space,
            },
        )
        if not include_baseline:
            candidates = [c for c in candidates if c.get("source") != "baseline"]

        ranked: list[dict[str, Any]] = []
        for candidate in candidates:
            try:
                result = self._run_backtest(
                    candidate["snapshot"], start_date, end_date
                )
            except Exception as exc:
                logger.error("structured_tune_backtest_failed", name=candidate.get("name"), error=str(exc))
                result = {}
            score = self.scoring_service.score_result(result, regime=regime)
            ranked.append({
                "name": candidate["name"],
                "reasoning": "",
                "source": candidate["source"],
                "overrides": candidate.get("overrides") or {},
                "snapshot": candidate["snapshot"],
                "score": score,
                "result": self._slim_result(result),
            })

        ranked = self.scoring_service.rank_results(ranked)
        best = ranked[0] if ranked else None
        elapsed = round(time.time() - t0, 1)
        global_best_score = float(
            (best or {}).get("score", {}).get("overallScore", 0) or 0
        )

        indicator_code = snapshot.get("code") or ""
        indicator_params = extract_indicator_params(indicator_code)

        return {
            "regime": regime,
            "generatorHints": self._build_generator_hints(regime) if regime else {},
            "indicatorParams": indicator_params,
            "rounds": [
                {
                    "round": 1,
                    "bestScore": global_best_score,
                    "globalBestScore": global_best_score,
                    "candidateCount": len(ranked),
                    "elapsed": elapsed,
                    "error": None,
                }
            ],
            "rankedStrategies": ranked[:50],
            "bestStrategyOutput": self._build_best_output(best),
            "experiment": {
                "totalRounds": 1,
                "totalCandidates": len(ranked),
                "globalBestScore": global_best_score,
                "mode": "structured",
                "method": method,
                "maxVariants": max_variants,
            },
        }

    # ── Save experiment result as strategy ────────────────────────────────

    def save_as_strategy(
        self,
        best_output: dict[str, Any],
        strategy_name: str,
        market_category: str = "Crypto",
    ) -> str:
        """Persist the best experiment candidate as a strategy record. Returns strategy ID."""
        from app.strategies.strategy_service import create_strategy

        snap = best_output.get("snapshot") or {}
        strategy_config = snap.get("strategy_config") or {}

        payload = {
            "strategy_name": strategy_name,
            "strategy_type": "IndicatorStrategy",
            "market_category": market_category,
            "execution_mode": "signal",
            "status": "stopped",
            "indicator_config": {
                "indicator_id": snap.get("indicator_id"),
                "code": snap.get("code"),
                "indicator_params": snap.get("indicator_params") or {},
            },
            "trading_config": {
                "symbol": snap.get("symbol"),
                "timeframe": snap.get("timeframe"),
                "initial_capital": snap.get("initial_capital", 10000),
                "leverage": snap.get("leverage", 1),
                "commission": snap.get("commission", 0),
                "slippage": snap.get("slippage", 0),
                "trade_direction": snap.get("trade_direction", "long"),
                "market_type": "swap",
                "strategy_config": strategy_config,
                "enable_mtf": snap.get("enable_mtf", True),
            },
            "exchange_config": {},
        }
        return create_strategy(payload)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _run_backtest(
        self,
        snapshot: dict[str, Any],
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """Run backtest from a snapshot dict, adapting to UF's BacktestService interface."""
        return self.backtest_service.run(
            indicator_code=snapshot.get("code") or "",
            market=snapshot.get("market") or "Crypto",
            symbol=snapshot.get("symbol") or "",
            timeframe=snapshot.get("timeframe") or "1D",
            start_date=start_date,
            end_date=end_date,
            initial_capital=float(snapshot.get("initial_capital") or 10000),
            commission=float(snapshot.get("commission") or 0),
            leverage=int(snapshot.get("leverage") or 1),
            trade_direction=str(snapshot.get("trade_direction") or "long"),
            strategy_config=snapshot.get("strategy_config"),
            indicator_params=snapshot.get("indicator_params"),
        )

    def _detect_regime(self, base: dict[str, Any]) -> dict[str, Any]:
        """Detect market regime by fetching klines and running regime analysis."""
        market = str(base.get("market") or "Crypto")
        symbol = str(base.get("symbol") or "")
        timeframe = str(base.get("timeframe") or "1D")
        start_date, end_date = self._parse_dates(base)

        # Fetch klines via backtest service's data fetcher
        df = self.backtest_service._fetch_kline_data(
            market, symbol, timeframe, start_date, end_date
        )

        # Convert DataFrame to list[dict] for regime service
        klines: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            klines.append({
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("volume", 0)),
            })

        return self.regime_service.detect(
            klines, symbol=symbol, market=market, timeframe=timeframe
        )

    def _build_snapshot(self, base: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
        """Build a backtest-ready snapshot from base config. Returns (snapshot, start_date, end_date)."""
        start_date, end_date = self._parse_dates(base)
        snapshot = copy.deepcopy(base.get("snapshot") or {})
        if not snapshot:
            snapshot = {
                "code": base.get("indicatorCode") or base.get("code") or "",
                "market": base.get("market") or "Crypto",
                "symbol": base.get("symbol") or "",
                "timeframe": base.get("timeframe") or "1D",
                "initial_capital": float(base.get("initialCapital") or 10000),
                "commission": float(base.get("commission") or 0),
                "slippage": float(base.get("slippage") or 0),
                "leverage": int(base.get("leverage") or 1),
                "trade_direction": str(base.get("tradeDirection") or "long"),
                "strategy_config": base.get("strategyConfig") or {},
                "indicator_params": base.get("indicatorParams") or {},
                "indicator_id": base.get("indicatorId"),
                "enable_mtf": bool(base.get("enableMtf", True)),
                "run_type": str(base.get("runType") or "indicator"),
            }
        return snapshot, start_date, end_date

    @staticmethod
    def _parse_dates(base: dict[str, Any]) -> tuple[str, str]:
        """Parse start/end dates from payload, returning string format."""
        start = str(base.get("startDate") or "")
        end = str(base.get("endDate") or "")
        if not start or not end:
            raise ValueError("startDate and endDate are required")
        return start, end

    @staticmethod
    def _apply_candidate_to_snapshot(
        base_snapshot: dict[str, Any],
        candidate: dict[str, Any],
        indicator_params_def: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a backtest snapshot by merging LLM candidate params."""
        snap = copy.deepcopy(base_snapshot)

        ind_params = candidate.get("indicatorParams") or {}
        if ind_params:
            snap["indicator_params"] = {**(snap.get("indicator_params") or {}), **ind_params}

        risk = candidate.get("riskParams") or {}
        sc = snap.get("strategy_config") or {}

        if risk.get("stopLossPct") is not None:
            sc.setdefault("risk", {})["stopLossPct"] = risk["stopLossPct"]
        if risk.get("takeProfitPct") is not None:
            sc.setdefault("risk", {})["takeProfitPct"] = risk["takeProfitPct"]
        if risk.get("entryPct") is not None:
            sc.setdefault("position", {})["entryPct"] = risk["entryPct"]

        trailing = risk.get("trailingStop") or {}
        if trailing.get("enabled"):
            sc.setdefault("risk", {})["trailing"] = {
                "enabled": True,
                "pct": trailing.get("pct", 0.02),
                "activationPct": trailing.get("activationPct", 0.01),
            }

        if risk.get("leverage") is not None:
            snap["leverage"] = int(risk["leverage"])

        snap["strategy_config"] = sc
        return snap

    def _build_candidates(
        self,
        *,
        base_snapshot: dict[str, Any],
        variants: list[dict[str, Any]],
        parameter_space: dict[str, Any],
        evolution: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build candidate list from baseline + manual variants + evolution."""
        candidates: list[dict[str, Any]] = [
            {
                "name": "baseline",
                "snapshot": copy.deepcopy(base_snapshot),
                "overrides": {},
                "source": "baseline",
            }
        ]

        for idx, variant in enumerate(variants, start=1):
            snapshot = copy.deepcopy(base_snapshot)
            overrides = variant.get("overrides") or variant
            for key, value in overrides.items():
                self.evolution_service._set_nested(
                    snapshot,
                    self.evolution_service._normalize_key(key).split("."),
                    value,
                )
            candidates.append({
                "name": str(variant.get("name") or f"candidate_{idx}"),
                "snapshot": snapshot,
                "overrides": overrides,
                "source": "manual_variant",
            })

        evo_conf = evolution or {}
        max_variants = int(evo_conf.get("maxVariants") or 0)
        effective_space = parameter_space or evo_conf.get("parameterSpace") or {}
        if effective_space:
            generated = self.evolution_service.build_variants(
                base_snapshot=base_snapshot,
                parameter_space=effective_space,
                max_variants=max_variants or 12,
                method=str(evo_conf.get("method") or "grid"),
            )
            candidates.extend(generated)

        # Deduplicate by snapshot fingerprint
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate.get("snapshot"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique

    @staticmethod
    def _slim_result(result: dict[str, Any]) -> dict[str, Any]:
        """Strip heavy fields to keep payload small."""
        if not result:
            return {}
        return {
            "totalReturn": result.get("totalReturn"),
            "annualReturn": result.get("annualReturn"),
            "maxDrawdown": result.get("maxDrawdown"),
            "sharpeRatio": result.get("sharpeRatio"),
            "profitFactor": result.get("profitFactor"),
            "winRate": result.get("winRate"),
            "totalTrades": result.get("totalTrades"),
        }

    @staticmethod
    def _emit(callback: Any | None, event: str, data: dict[str, Any]) -> None:
        if callback:
            try:
                callback({"event": event, **data})
            except Exception:
                pass

    @staticmethod
    def _build_generator_hints(regime: dict[str, Any]) -> dict[str, Any]:
        families = regime.get("strategyFamilies") or []
        return {
            "preferredFamilies": families[:3],
            "regime": regime.get("regime"),
            "promptHint": (
                f"Focus on {', '.join(families[:2]) or 'robust'} setups under "
                f"{regime.get('label') or 'current'} conditions with risk controls."
            ),
        }

    @staticmethod
    def _build_best_output(best: dict[str, Any] | None) -> dict[str, Any] | None:
        if not best:
            return None
        return {
            "name": best.get("name"),
            "score": best.get("score"),
            "source": best.get("source"),
            "overrides": best.get("overrides"),
            "snapshot": best.get("snapshot"),
            "summary": {
                "totalReturn": (best.get("result") or {}).get("totalReturn"),
                "maxDrawdown": (best.get("result") or {}).get("maxDrawdown"),
                "sharpeRatio": (best.get("result") or {}).get("sharpeRatio"),
                "totalTrades": (best.get("result") or {}).get("totalTrades"),
            },
        }
