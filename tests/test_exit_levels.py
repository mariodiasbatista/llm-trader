"""Tests for strategies/exit_levels.py + the adaptive take-profit wiring in trailing_stop."""
import pytest
from unittest.mock import patch, MagicMock

from strategies.exit_levels import (
    mfe_distribution,
    reach_rate,
    level_at_reach_probability,
    resolve_take_profit,
)


def _bars(closes, highs=None):
    highs = highs if highs is not None else closes
    out = []
    for c, h in zip(closes, highs):
        b = MagicMock()
        b.close = c
        b.high = h
        out.append(b)
    return out


ACFG = {
    "enabled": True,
    "keep_flat_reach_pct": 50,
    "target_reach_probability": 0.7,
    "min_windows": 3,
    "tp_min": 0.03,
    "tp_max": 0.60,
}


class TestMfeDistribution:
    def test_computes_forward_max_gain_per_window(self):
        # flat 100s with a spike to 110 at index 3
        bars = _bars([100, 100, 100, 100, 100], highs=[100, 100, 100, 110, 100])
        d = mfe_distribution(bars, horizon_days=2)
        # windows start at i=0,1,2 → i=1 and i=2 both see the 110 spike ahead
        assert len(d) == 3
        assert max(d) == pytest.approx(10.0)

    def test_horizon_limits_lookahead(self):
        bars = _bars([100] * 10, highs=[100] * 9 + [200])
        # with a 2-day horizon, only the last couple of windows can see the spike
        d = mfe_distribution(bars, horizon_days=2)
        assert sum(1 for x in d if x > 50) <= 2

    def test_skips_nonpositive_base(self):
        bars = _bars([0, 100, 100, 100], highs=[0, 110, 110, 110])
        d = mfe_distribution(bars, horizon_days=1)
        assert all(isinstance(x, float) for x in d)

    def test_too_few_bars_yields_empty(self):
        assert mfe_distribution(_bars([100, 100]), horizon_days=20) == []


class TestReachRate:
    def test_share_of_windows_reaching_level(self):
        assert reach_rate([0.0, 5.0, 10.0, 20.0], 10) == pytest.approx(50.0)

    def test_none_on_empty(self):
        assert reach_rate([], 10) is None


class TestLevelAtReachProbability:
    def test_high_probability_gives_modest_level(self):
        dist = sorted([1.0, 2.0, 3.0, 10.0, 20.0])
        easy = level_at_reach_probability(dist, 0.9)
        hard = level_at_reach_probability(dist, 0.1)
        assert easy < hard, "a level reached 90% of the time must be lower than one reached 10%"

    def test_none_on_empty(self):
        assert level_at_reach_probability([], 0.7) is None


class TestResolveTakeProfit:
    def test_keeps_flat_target_when_reachable(self):
        # every window reaches +20% → flat 12% is comfortably reachable
        dist = [20.0] * 10
        assert resolve_take_profit(dist, 0.12, ACFG) == pytest.approx(0.12)

    def test_lowers_target_when_flat_unreachable(self):
        # nothing ever gets near 12% → must fall back to what the stock does reach
        dist = [1.0, 2.0, 3.0, 4.0, 5.0]
        tp = resolve_take_profit(dist, 0.12, ACFG)
        assert tp is not None and tp < 0.12

    def test_returns_none_on_insufficient_history(self):
        assert resolve_take_profit([1.0], 0.12, ACFG) is None
        assert resolve_take_profit([], 0.12, ACFG) is None

    def test_respects_clamps(self):
        tiny = resolve_take_profit([0.01] * 10, 0.12, ACFG)
        assert tiny == pytest.approx(ACFG["tp_min"])
        huge = resolve_take_profit([500.0] * 10, 0.99, {**ACFG, "keep_flat_reach_pct": 101})
        assert huge == pytest.approx(ACFG["tp_max"])


# ── wiring into trailing_stop ────────────────────────────────────────────────

BASE_CFG = {
    "initial_stop_pct": 0.15,
    "trailing_pct": 0.15,
    "take_profit_pct": 0.12,
    "profit_target_pct": 0.03,
    "trailing_pct_from_profit": 0.05,
    "ladder_buys": [],
    "adaptive_take_profit": ACFG,
}


class TestAdaptiveTakeProfitFetch:
    @patch("strategies.trailing_stop.get_bars_range", side_effect=RuntimeError("api down"))
    def test_fetch_failure_falls_back_to_flat(self, _mock):
        from strategies.trailing_stop import _adaptive_take_profit
        assert _adaptive_take_profit("AAPL", BASE_CFG) is None

    @patch("strategies.trailing_stop.get_bars_range")
    def test_disabled_skips_fetch_entirely(self, mock_bars):
        from strategies.trailing_stop import _adaptive_take_profit
        cfg = {**BASE_CFG, "adaptive_take_profit": {**ACFG, "enabled": False}}
        assert _adaptive_take_profit("AAPL", cfg) is None
        mock_bars.assert_not_called()


class TestPositionCfgStamping:
    @patch("strategies.trailing_stop.get_bars_range")
    def test_stamps_adaptive_tp_on_new_position(self, mock_bars):
        from strategies.trailing_stop import _position_cfg
        mock_bars.return_value = _bars([100] * 60, highs=[102] * 60)  # ~2% moves, 12% unreachable
        ps = {"entry_price": 100.0}
        cfg = _position_cfg("AAPL", BASE_CFG, ps)
        assert "adaptive_tp" in ps
        assert cfg["take_profit_pct"] == ps["adaptive_tp"] < 0.12

    @patch("strategies.trailing_stop.get_bars_range")
    def test_reuses_stamp_without_refetching(self, mock_bars):
        from strategies.trailing_stop import _position_cfg
        ps = {"entry_price": 100.0, "adaptive_tp": 0.055, "high_water_mark": 100.0}
        cfg = _position_cfg("AAPL", BASE_CFG, ps)
        assert cfg["take_profit_pct"] == pytest.approx(0.055)
        mock_bars.assert_not_called(), "a stamped position must not re-derive its target"

    @patch("strategies.trailing_stop.get_bars_range")
    def test_pre_existing_position_keeps_flat_target(self, mock_bars):
        """Positions already tracked before this feature shipped must not have their
        exit target changed mid-trade — that could force-close open winners."""
        from strategies.trailing_stop import _position_cfg
        ps = {"entry_price": 100.0, "high_water_mark": 110.0, "stop_floor": 93.5}
        cfg = _position_cfg("AAPL", BASE_CFG, ps)
        assert cfg["take_profit_pct"] == pytest.approx(0.12)
        assert "adaptive_tp" not in ps
        mock_bars.assert_not_called()

    @patch("strategies.trailing_stop.get_bars_range", side_effect=RuntimeError("api down"))
    def test_falls_back_to_flat_and_does_not_stamp_on_failure(self, _mock):
        from strategies.trailing_stop import _position_cfg
        ps = {"entry_price": 100.0}
        cfg = _position_cfg("AAPL", BASE_CFG, ps)
        assert cfg["take_profit_pct"] == pytest.approx(0.12)
        assert "adaptive_tp" not in ps, "a failed derivation must retry next cycle, not stamp a guess"


class TestBackwardCompatibility:
    @patch("strategies.trailing_stop.get_bars_range")
    def test_config_without_adaptive_block_behaves_as_before(self, mock_bars):
        from strategies.trailing_stop import _position_cfg
        legacy = {k: v for k, v in BASE_CFG.items() if k != "adaptive_take_profit"}
        ps = {"entry_price": 100.0}
        cfg = _position_cfg("AAPL", legacy, ps)
        assert cfg["take_profit_pct"] == pytest.approx(0.12)
        assert "adaptive_tp" not in ps
        mock_bars.assert_not_called()
