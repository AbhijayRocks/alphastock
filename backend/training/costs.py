"""
training/costs.py — Realistic transaction-cost model for NSE equities.

WHY THIS MATTERS (Tier 0 trust):
  A flat "0.1% per trade" hides where strategies actually die. Real costs for an
  Indian equity long/short stack up from several components, and market impact
  grows with size (square-root law). Most thin "edges" evaporate once you charge
  honestly — better to know in the backtest than in production.

COMPONENTS (per side unless noted), in basis points (1 bp = 0.01%):
  • brokerage          : discount broker ~3 bps
  • exchange txn charge : ~0.3 bps
  • SEBI + stamp        : ~1.5 bps (stamp on buy only; folded in conservatively)
  • STT                 : 10 bps on the SELL side (delivery equity)
  • GST                 : 18% on (brokerage + exchange charges)
  • slippage            : ~5 bps for liquid Nifty names (wider for small caps)
  • market impact       : c · σ · sqrt(participation),  participation = Q / ADV
"""

from dataclasses import dataclass
import numpy as np

_BPS = 1e-4


@dataclass
class CostModel:
    brokerage_bps: float = 3.0
    exchange_bps: float = 0.3
    sebi_stamp_bps: float = 1.5
    stt_sell_bps: float = 10.0          # charged on sell side only
    gst_rate: float = 0.18
    slippage_bps: float = 5.0
    impact_coef: float = 0.1            # square-root-law coefficient
    participation: float = 0.02         # order size as fraction of ADV

    def _fixed_per_side(self, is_sell: bool) -> float:
        """Fixed (size-independent) cost for one side, in bps."""
        gst = self.gst_rate * (self.brokerage_bps + self.exchange_bps)
        stt = self.stt_sell_bps if is_sell else 0.0
        return self.brokerage_bps + self.exchange_bps + self.sebi_stamp_bps + stt + gst + self.slippage_bps

    def round_trip_bps(self, daily_vol: float = 0.02) -> float:
        """
        Total round-trip cost (buy + sell) in bps, including market impact.
        `daily_vol` is the asset's daily return volatility (for the impact term).
        """
        fixed = self._fixed_per_side(is_sell=False) + self._fixed_per_side(is_sell=True)
        impact = self.impact_coef * (daily_vol / _BPS) * np.sqrt(self.participation)  # bps
        return fixed + impact

    def cost_fraction(self, turnover: float, daily_vol: float = 0.02) -> float:
        """
        Cost as a return fraction for a given `turnover` (1.0 = fully replace the
        position). Round-trip cost is split across the implied buy+sell.
        """
        return turnover * self.round_trip_bps(daily_vol) * _BPS


# Sensible default for liquid Nifty-50 names (~25-30 bps round trip + impact)
DEFAULT_COSTS = CostModel()


if __name__ == "__main__":
    cm = DEFAULT_COSTS
    for vol in (0.01, 0.02, 0.04):
        print(f"daily_vol={vol:.0%}: round-trip ≈ {cm.round_trip_bps(vol):.1f} bps")
