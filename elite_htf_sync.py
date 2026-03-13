# elite_htf_sync.py
# V32 ELITE — HTF Synchronization Engine
#
# Исправления vs V31:
#   1. _ema: неправильная инициализация (использовался closes[0] как seed)
#      → исправлено: seed = среднее первых `period` свечей (SMA seed)
#   2. _bias: порог разницы EMA (добавлен min_gap чтобы избежать ложных сигналов)
#   3. _exhaustion: добавлена проверка на минимальный диапазон (фильтр флета)
#   4. _combine_bias: добавлен weighted bias (4h весомее 1h весомее 15m)
#   5. _htf_regime: улучшена классификация

from typing import List, Dict, Optional


class EliteHTFSync:

    def __init__(
        self,
        min_len_15m: int = 200,
        min_len_1h:  int = 120,
        min_len_4h:  int = 80
    ):
        self.min_len_15m = min_len_15m
        self.min_len_1h  = min_len_1h
        self.min_len_4h  = min_len_4h

    # ==========================================================
    # PUBLIC ENTRY
    # ==========================================================

    def analyze(
        self,
        current_timestamp: int,
        tf15: List[Dict],
        tf1h: List[Dict],
        tf4h: List[Dict]
    ) -> Optional[Dict]:

        idx15 = self._last_index_leq(tf15, current_timestamp)
        idx1h = self._last_index_leq(tf1h, current_timestamp)
        idx4h = self._last_index_leq(tf4h, current_timestamp)

        if idx15 is None or idx1h is None or idx4h is None:
            return None

        hist15 = tf15[:idx15 + 1]
        hist1h = tf1h[:idx1h + 1]
        hist4h = tf4h[:idx4h + 1]

        if (
            len(hist15) < self.min_len_15m
            or len(hist1h) < self.min_len_1h
            or len(hist4h) < self.min_len_4h
        ):
            return None

        bias15 = self._bias(hist15)
        bias1h = self._bias(hist1h)
        bias4h = self._bias(hist4h)

        strength15 = self._trend_strength(hist15)
        strength1h = self._trend_strength(hist1h)
        strength4h = self._trend_strength(hist4h)

        s15 = self._signed_strength(bias15, strength15)
        s1h = self._signed_strength(bias1h, strength1h)
        s4h = self._signed_strength(bias4h, strength4h)

        exhausted15 = self._exhaustion(hist15)
        exhausted1h = self._exhaustion(hist1h)
        exhausted4h = self._exhaustion(hist4h)

        # Weighted bias (4h имеет наибольший вес)
        bias, alignment = self._combine_bias_weighted(bias15, bias1h, bias4h)

        exhausted_any = exhausted15 or exhausted1h or exhausted4h

        # Weighted signed strength
        avg_signed_strength = (s15 * 0.20 + s1h * 0.35 + s4h * 0.45)
        avg_strength        = (strength15 * 0.20 + strength1h * 0.35 + strength4h * 0.45)

        if exhausted_any:
            alignment           *= 0.60
            avg_strength        *= 0.70
            avg_signed_strength *= 0.70

        htf_regime = self._htf_regime(bias, avg_strength, alignment)

        return {
            "bias":                 bias,
            "alignment_score":      alignment,
            "trend_strength":       avg_strength,
            "signed_trend_strength":avg_signed_strength,
            "exhausted":            exhausted_any,
            "htf_regime":           htf_regime,
            "details": {
                "bias_15m":       bias15,
                "bias_1h":        bias1h,
                "bias_4h":        bias4h,
                "strength_15m":   strength15,
                "strength_1h":    strength1h,
                "strength_4h":    strength4h,
                "exhausted_15m":  exhausted15,
                "exhausted_1h":   exhausted1h,
                "exhausted_4h":   exhausted4h,
            }
        }

    # ==========================================================
    # BINARY SEARCH — no lookahead
    # ==========================================================

    def _last_index_leq(self, candles: List[Dict], ts: int) -> Optional[int]:
        last_idx = None
        for i, c in enumerate(candles):
            if c["timestamp"] <= ts:
                last_idx = i
            else:
                break
        return last_idx

    # ==========================================================
    # BIAS  (исправлен EMA + добавлен min_gap)
    # ==========================================================

    def _bias(self, candles: List[Dict]) -> str:
        closes = [float(c["close"]) for c in candles]
        if len(closes) < 200:
            return "neutral"

        ema50  = self._ema(closes, 50)
        ema200 = self._ema(closes, 200)
        price  = closes[-1]

        if price <= 0:
            return "neutral"

        # минимальный разрыв 0.1% чтобы не шуметь в боковике
        gap = abs(ema50 - ema200) / price
        if gap < 0.001:
            return "neutral"

        if ema50 > ema200:
            return "bullish"
        elif ema50 < ema200:
            return "bearish"
        return "neutral"

    # ==========================================================
    # TREND STRENGTH
    # ==========================================================

    def _trend_strength(self, candles: List[Dict]) -> float:
        closes = [float(c["close"]) for c in candles]
        if len(closes) < 60:
            return 0.0

        ema20 = self._ema(closes, 20)
        ema50 = self._ema(closes, 50)
        price = closes[-1]

        if price <= 0:
            return 0.0

        return abs(ema20 - ema50) / price

    def _signed_strength(self, bias: str, strength: float) -> float:
        if bias == "bullish":
            return strength
        if bias == "bearish":
            return -strength
        return 0.0

    # ==========================================================
    # EXHAUSTION
    # ==========================================================

    def _exhaustion(self, candles: List[Dict]) -> bool:
        if len(candles) < 40:
            return False

        recent = candles[-20:]
        highs  = [float(c["high"])  for c in recent]
        lows   = [float(c["low"])   for c in recent]
        closes = [float(c["close"]) for c in recent]

        total_range = max(highs) - min(lows)
        net_move    = abs(closes[-1] - closes[0])

        if total_range < closes[0] * 0.005:   # диапазон < 0.5% цены → не считаем
            return False

        efficiency = net_move / total_range
        return efficiency < 0.25   # строже чем 0.30

    # ==========================================================
    # WEIGHTED BIAS COMBINE
    # ==========================================================

    def _combine_bias_weighted(self, b15: str, b1h: str, b4h: str):
        """
        Веса: 4h=0.50, 1h=0.35, 15m=0.15
        """
        weights = {"15m": 0.15, "1h": 0.35, "4h": 0.50}
        biases  = {"15m": b15,  "1h": b1h,  "4h": b4h}

        bull_score = bear_score = 0.0
        for tf, b in biases.items():
            w = weights[tf]
            if b == "bullish":
                bull_score += w
            elif b == "bearish":
                bear_score += w

        if bull_score >= 0.50:
            return "bullish", bull_score
        if bear_score >= 0.50:
            return "bearish", bear_score

        return "neutral", max(bull_score, bear_score) * 0.5

    # ==========================================================
    # HTF REGIME
    # ==========================================================

    def _htf_regime(self, bias: str, strength: float, alignment: float) -> str:
        if alignment >= 0.66 and strength > 0.010 and bias in ("bullish", "bearish"):
            return "HTF_TREND"
        if alignment >= 0.50 and strength > 0.005 and bias in ("bullish", "bearish"):
            return "HTF_WEAK_TREND"
        if strength < 0.003 or alignment < 0.35:
            return "HTF_RANGE"
        return "HTF_CONTRA"

    # ==========================================================
    # EMA — ИСПРАВЛЕНА (SMA seed вместо closes[0])
    # ==========================================================

    def _ema(self, closes: List[float], period: int) -> float:
        if len(closes) < period:
            return closes[-1]

        k   = 2.0 / (period + 1)
        # Правильный seed: SMA по первым `period` значениям
        ema = sum(closes[:period]) / period

        for price in closes[period:]:
            ema = price * k + ema * (1 - k)

        return ema
