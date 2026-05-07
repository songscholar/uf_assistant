"""
UF Stock Assistant — Strategy Evolution Service

Generate strategy parameter variants via grid or random search.
Adapted from QuantDinger with minimal changes.
"""

from __future__ import annotations

import copy
import itertools
import random
from typing import Any


class StrategyEvolutionService:
    """Generate strategy variants from structured parameter spaces."""

    def build_variants(
        self,
        *,
        base_snapshot: dict[str, Any],
        parameter_space: dict[str, Any] | None = None,
        max_variants: int = 12,
        method: str = "grid",
    ) -> list[dict[str, Any]]:
        """
        Generate parameter variants for backtest optimization.

        Args:
            base_snapshot: Base strategy snapshot to mutate.
            parameter_space: Dict mapping parameter paths to value specs.
                Keys are dot-separated paths (e.g. "strategy_config.risk.stopLossPct").
                Values can be: list of values, or dict with min/max/step.
            max_variants: Maximum number of variants to generate.
            method: "grid" (cartesian product) or "random" (random sampling).

        Returns:
            List of variant dicts with keys: name, snapshot, overrides, source.
        """
        if not parameter_space:
            return []

        normalized_space = {
            self._normalize_key(path): self._resolve_values(spec)
            for path, spec in parameter_space.items()
            if self._resolve_values(spec)
        }
        if not normalized_space:
            return []

        if method == "random":
            return self._random_variants(base_snapshot, normalized_space, max_variants=max_variants)
        return self._grid_variants(base_snapshot, normalized_space, max_variants=max_variants)

    def _grid_variants(
        self,
        base_snapshot: dict[str, Any],
        normalized_space: dict[str, list[Any]],
        *,
        max_variants: int,
    ) -> list[dict[str, Any]]:
        """Generate all combinations via cartesian product."""
        keys = list(normalized_space.keys())
        variants: list[dict[str, Any]] = []
        for idx, values in enumerate(
            itertools.product(*(normalized_space[key] for key in keys)), start=1
        ):
            snapshot = copy.deepcopy(base_snapshot)
            overrides: dict[str, Any] = {}
            for key, value in zip(keys, values):
                self._set_nested(snapshot, key.split("."), value)
                overrides[key] = value
            variants.append({
                "name": f"variant_{idx}",
                "snapshot": snapshot,
                "overrides": overrides,
                "source": "evolution_grid",
            })
            if len(variants) >= max_variants:
                break
        return variants

    def _random_variants(
        self,
        base_snapshot: dict[str, Any],
        normalized_space: dict[str, list[Any]],
        *,
        max_variants: int,
    ) -> list[dict[str, Any]]:
        """Generate random parameter combinations."""
        keys = list(normalized_space.keys())
        variants: list[dict[str, Any]] = []
        for idx in range(1, max_variants + 1):
            snapshot = copy.deepcopy(base_snapshot)
            overrides: dict[str, Any] = {}
            for key in keys:
                value = random.choice(normalized_space[key])
                self._set_nested(snapshot, key.split("."), value)
                overrides[key] = value
            variants.append({
                "name": f"variant_{idx}",
                "snapshot": snapshot,
                "overrides": overrides,
                "source": "evolution_random",
            })
        return variants

    @staticmethod
    def _resolve_values(spec: Any) -> list[Any]:
        """Resolve a parameter spec into a list of concrete values."""
        if isinstance(spec, list):
            return spec
        if isinstance(spec, tuple):
            return list(spec)
        if isinstance(spec, dict):
            minimum = spec.get("min")
            maximum = spec.get("max")
            step = spec.get("step", 1)
            if minimum is None or maximum is None:
                return []
            values: list[Any] = []
            cursor = minimum
            if step == 0:
                return [minimum]
            while cursor <= maximum:
                values.append(round(cursor, 10) if isinstance(cursor, float) else cursor)
                cursor += step
            return values
        return [spec]

    @staticmethod
    def _normalize_key(path: str) -> str:
        """Normalize parameter path for consistent lookup."""
        path = str(path or "").strip()
        return path.replace("strategyConfig.", "strategy_config.")

    @staticmethod
    def _set_nested(target: dict[str, Any], parts: list[str], value: Any) -> None:
        """Set a value in a nested dict using a list of key parts."""
        cursor = target
        for part in parts[:-1]:
            if part not in cursor or not isinstance(cursor[part], dict):
                cursor[part] = {}
            cursor = cursor[part]
        cursor[parts[-1]] = value
