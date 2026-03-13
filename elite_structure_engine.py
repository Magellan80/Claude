# elite_structure_engine.py
# V32.1 ELITE — Microstructure Engine (with recent_candles support)

from typing import List, Dict, Optional


class EliteStructureEngine:

    def __init__(self, swing_window: int = 3):
        self.swing_window = swing_window

        self.min_swings  = 6
        self.min_candles = 120

        self.min_clarity  = 0.35
        self.min_impulse  = 0.25
        self.min_pullback = 0.25

    # ==========================================================
    # PUBLIC ENTRY
    # ==========================================================

    def analyze(self, candles: List[Dict]) -> Optional[Dict]:
        if len(candles) < self.min_candles:
            return None

        atr = self._atr(candles, 14)
        if not atr or atr <= 0:
            return None

        swings = self._detect_swings(candles)
        if len(swings) < self.min_swings:
            return None

        structure_state = self._classify_structure(swings)
        impulse         = self._impulse_strength(candles, atr)
        pullback        = self._pullback_quality(candles)
        clarity         = self._structure_clarity(swings, atr)
        momentum_decay  = self._momentum_decay(candles)

        if clarity < self.min_clarity:
            return None
        if impulse < self.min_impulse:
            return None
        if pullback < self.min_pullback:
            return None

        # micro_reversal для EliteReversalEngine
        micro_confirmed, micro_score = self._micro_reversal(candles, atr)

        # recent candles for Trend/Reversal/Router
        recent_candles = candles[-20:]
        recent_highs   = [c["high"] for c in recent_candles]
        recent_lows    = [c["low"]  for c in recent_candles]

        return {
            "structure":            structure_state,
            "impulse_strength":     impulse,
            "pullback_quality":     pullback,
            "clarity_index":        clarity,
            "momentum_decay":       momentum_decay,
            "micro_confirmed":      micro_confirmed,
            "micro_reversal_score": micro_score,

            # NEW — required by TrendEngine, ReversalEngine, Router
            "recent_candles": recent_candles,
            "recent_highs":   recent_highs,
            "recent_lows":    recent_lows,
            "swings":         swings[-12:],   # last swings for context
        }

    # ==========================================================
    # SWING DETECTION
    # ==========================================================

    def _detect_swings(self, candles: List[Dict]) -> List[Dict]:
        swings = []
        w = self.swing_window

        for i in range(w, len(candles) - w):
            high = float(candles[i]["high"])
            low  = float(candles[i]["low"])

            if all(
                float(candles[i - j]["high"]) < high and
                float(candles[i + j]["high"]) < high
                for j in range(1, w + 1)
            ):
                swings.append({"type": "high", "price": high, "index": i})

            if all(
                float(candles[i - j]["low"]) > low and
                float(candles[i + j]["low"]) > low
                for j in range(1, w + 1)
            ):
                swings.append({"type": "low", "price": low, "index": i})

        return swings

    # ==========================================================
    # STRUCTURE CLASSIFICATION
    # ==========================================================

    def _classify_structure(self, swings: List[Dict]) -> str:
        recent = swings[-6:]
        highs  = [s for s in recent if s["type"] == "high"]
        lows   = [s for s in recent if s["type"] == "low"]

        if len(highs) < 2 or len(lows) < 2:
            return "neutral"

        hh = highs[-1]["price"] > highs[-2]["price"]
        hl = lows[-1]["price"]  > lows[-2]["price"]
        lh = highs[-1]["price"] < highs[-2]["price"]
        ll = lows[-1]["price"]  < lows[-2]["price"]

        if hh and hl:
            return "bullish"
        if lh and ll:
            return "bearish"
        return "range"

    # ==========================================================
    # IMPULSE STRENGTH
    # ==========================================================

    def _impulse_strength(self, candles: List[Dict], atr: float) -> float:
        recent = candles[-12:]
        move   = abs(float(recent[-1]["close"]) - float(recent[0]["open"]))
        return max(0.0, min(move / atr, 3.0)) if atr > 0 else 0.0

    # ==========================================================
    # PULLBACK QUALITY
    # ==========================================================

    def _pullback_quality(self, candles: List[Dict]) -> float:
        recent = candles[-15:]
        closes = [float(c["close"]) for c in recent]

        max_close   = max(closes)
        min_close   = min(closes)
        total_move  = max_close - min_close

        if total_move <= 0:
            return 0.0

        retrace = abs(closes[-1] - max_close)
        depth   = retrace / total_move

        return max(0.0, min(1.0 - abs(depth - 0.40) * 2, 1.0))

    # ==========================================================
    # MOMENTUM DECAY
    # ==========================================================

    def _momentum_decay(self, candles: List[Dict]) -> bool:
        closes = [float(c["close"]) for c in candles[-8:]]
        diffs  = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

        if len(diffs) < 4:
            return False

        first = sum(diffs[:3]) / 3
        last  = sum(diffs[-3:]) / 3

        if abs(first) < 1e-8:
            return False

        return abs(last) < abs(first) * 0.7

    # ==========================================================
    # STRUCTURE CLARITY
    # ==========================================================

    def _structure_clarity(self, swings: List[Dict], atr: float) -> float:
        if len(swings) < 4 or atr <= 0:
            return 0.0

        moves = [
            abs(swings[i]["price"] - swings[i - 1]["price"])
            for i in range(1, len(swings))
        ]

        avg     = sum(moves[-4:]) / 4
        clarity = avg / (atr * 2)
        return max(0.0, min(clarity, 1.0))

    # ==========================================================
    # MICRO REVERSAL
    # ==========================================================

    def _micro_reversal(self, candles: List[Dict], atr: float):
        if len(candles) < 3 or atr <= 0:
            return False, 0.0

        c = candles[-1]
        o = float(c["open"])
        h = float(c["high"])
        l = float(c["low"])
        cl= float(c["close"])

        body        = abs(cl - o)
        upper_wick  = h - max(cl, o)
        lower_wick  = min(cl, o) - l
        total_range = h - l

        if total_range <= 0:
            return False, 0.0

        bullish_pin = (lower_wick > body * 2.0) and (lower_wick > upper_wick * 2.0)
        bearish_pin = (upper_wick > body * 2.0) and (upper_wick > lower_wick * 2.0)

        micro_confirmed = bullish_pin or bearish_pin

        score = 0.0
        if micro_confirmed:
            wick_ratio = max(lower_wick, upper_wick) / total_range
            score = min(wick_ratio, 1.0)

        return micro_confirmed, score

    # ==========================================================
    # ATR
    # ==========================================================

    def _atr(self, candles: List[Dict], period: int) -> Optional[float]:
        trs = []
        for i in range(1, len(candles)):
            high = float(candles[i]["high"])
            low  = float(candles[i]["low"])
            prev = float(candles[i - 1]["close"])
            tr   = max(high - low, abs(high - prev), abs(low - prev))
            trs.append(tr)

        if len(trs) < period:
            return None

        return sum(trs[-period:]) / period
