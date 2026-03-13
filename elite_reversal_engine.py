# elite_reversal_engine.py
# V33 ELITE — Reversal Engine Adaptive (Volatility & Symbol Aware)

from typing import Dict, Optional


class EliteReversalEngine:

    def __init__(self):
        # Базовые fallback-пороги
        self.base_min_quality = 0.55
        self.base_min_clarity = 0.35
        self.base_min_impulse = 0.10

    # ==========================================================
    # PUBLIC ENTRY
    # ==========================================================

    def evaluate(self, structure: Dict, regime: Dict, htf: Dict, symbol: str = "BTCUSDT") -> Optional[Dict]:

        if not structure or not regime or not htf:
            return None

        # Адаптивные пороги под волатильность и символ
        thresholds = self._adaptive_thresholds(structure, regime, htf, symbol)
        min_clarity = thresholds["min_clarity"]
        min_impulse = thresholds["min_impulse"]
        min_micro = thresholds["min_micro"]
        min_atr = thresholds["min_atr"]
        min_quality = thresholds["min_quality"]

        # Определяем направление
        direction = self._direction(structure, regime, htf, symbol)
        if not direction:
            return None

        clarity = float(structure.get("clarity_index", 0.0))
        impulse = float(structure.get("impulse_strength", 0.0))
        micro_score = float(structure.get("micro_reversal_score", 0.0))
        micro_confirmed = bool(structure.get("micro_confirmed", False))
        atr_eff = self._effective_atr(regime)
        htf_exhausted = bool(htf.get("exhausted", False))

        # ------------------------------------------------------
        # Фильтры качества
        # ------------------------------------------------------
        if clarity < min_clarity:
            return None
        if impulse < min_impulse:
            return None
        if micro_score < min_micro:
            return None
        if not micro_confirmed:
            return None

        # ATR-контекст
        if atr_eff < min_atr and not htf_exhausted:
            return None

        # ------------------------------------------------------
        # LOCAL IMPULSE FILTER (адаптивный)
        # ------------------------------------------------------
        if not self._local_impulse_ok(structure, direction, symbol):
            return None

        # ------------------------------------------------------
        # QUALITY SCORE
        # ------------------------------------------------------
        quality = self._quality_score(structure, regime, htf, symbol)
        if quality < min_quality:
            return None

        return {
            "signal": direction,
            "quality": quality,
            "type": "reversal"
        }

    # ==========================================================
    # ADAPTIVE THRESHOLDS
    # ==========================================================

    def _adaptive_thresholds(self, structure: Dict, regime: Dict, htf: Dict, symbol: str):

        atr_p = float(regime.get("atr_percentile", 0.5))
        symbol_upper = symbol.upper()

        is_btc = symbol_upper.startswith("BTC")
        is_high_vol = symbol_upper.startswith(("DOGE", "SOL", "OP", "ARB", "AVAX"))

        # Базовые
        min_clarity = self.base_min_clarity
        min_impulse = self.base_min_impulse
        min_micro = 0.25
        min_atr = 0.40
        min_quality = self.base_min_quality

        # High-vol монеты
        if atr_p > 0.60:
            min_clarity = 0.30
            min_impulse = 0.08
            min_micro = 0.20
            min_atr = 0.30
            min_quality = 0.50

        # Medium-vol
        elif atr_p > 0.30:
            min_clarity = 0.35
            min_impulse = 0.10
            min_micro = 0.25
            min_atr = 0.35
            min_quality = 0.52

        # Low-vol (BTC, BNB)
        else:
            min_clarity = 0.40
            min_impulse = 0.12
            min_micro = 0.30
            min_atr = 0.40
            min_quality = 0.60

        # BTC всегда чуть строже
        if is_btc:
            min_clarity += 0.03
            min_impulse += 0.02
            min_micro += 0.05
            min_quality += 0.05

        return {
            "min_clarity": min_clarity,
            "min_impulse": min_impulse,
            "min_micro": min_micro,
            "min_atr": min_atr,
            "min_quality": min_quality,
        }

    # ==========================================================
    # DIRECTION LOGIC (Adaptive)
    # ==========================================================

    def _direction(self, structure: Dict, regime: Dict, htf: Dict, symbol: str) -> Optional[str]:

        local_structure = structure.get("structure")
        signed_strength = float(htf.get("signed_trend_strength", 0.0))
        regime_name = str(regime.get("regime", "RANGE")).upper()

        # Запрет реверсалов в сильном тренде
        if regime_name in ["STRONG_TREND", "EXPANSION"] and abs(signed_strength) > 0.012:
            return None

        # Классический reversal
        if local_structure == "bearish":
            return "long"
        if local_structure == "bullish":
            return "short"

        # Neutral → только при сильном exhaustion
        impulse = float(structure.get("impulse_strength", 0.0))
        if local_structure == "neutral" and impulse > 0.12:
            return "long" if signed_strength < 0 else "short"

        return None

    # ==========================================================
    # QUALITY SCORE (Adaptive)
    # ==========================================================

    def _quality_score(self, structure: Dict, regime: Dict, htf: Dict, symbol: str) -> float:

        clarity = float(structure.get("clarity_index", 0.0))
        impulse = float(structure.get("impulse_strength", 0.0))
        atr_eff = self._effective_atr(regime)
        alignment = float(htf.get("alignment_score", 0.5))
        micro_score = float(structure.get("micro_reversal_score", 0.0))
        htf_exhausted = bool(htf.get("exhausted", False))
        regime_name = str(regime.get("regime", "RANGE")).upper()

        score = 0.0

        # 1. Чистота структуры
        score += clarity * 0.30

        # 2. Импульс (нормализованный)
        score += min(impulse / 2.0, 1.0) * 0.25

        # 3. ATR-контекст
        score += atr_eff * 0.20

        # 4. Exhaustion
        if regime_name == "EXHAUSTION":
            score += 0.12
        if htf_exhausted:
            score += 0.10

        # 5. Alignment (низкий alignment = больше шанс разворота)
        if alignment < 0.45:
            score += 0.10
        elif alignment < 0.60:
            score += 0.05

        # 6. Micro-structure
        score += min(micro_score, 1.0) * 0.12

        # 7. Noise penalty
        noise_penalty = max(0.0, 0.20 - clarity)
        score -= noise_penalty * 0.15

        return max(0.0, min(score, 1.0))

    # ==========================================================
    # LOCAL IMPULSE FILTER (Adaptive)
    # ==========================================================

    def _local_impulse_ok(self, structure: Dict, direction: str, symbol: str) -> bool:

        candles = structure.get("recent_candles", [])
        if len(candles) < 5:
            return True

        closes = [c["close"] for c in candles[-5:]]
        highs  = [c["high"]  for c in candles[-5:]]
        lows   = [c["low"]   for c in candles[-5:]]

        last_close = closes[-1]

        sma5 = sum(closes[-5:]) / 5

        ema8 = closes[-1]
        for c in closes[-5:]:
            ema8 = ema8 * 0.7 + c * 0.3

        symbol_upper = symbol.upper()
        is_btc = symbol_upper.startswith("BTC")

        # LONG reversal
        if direction == "long":

            if closes[-1] > closes[-2] > closes[-3]:
                return False

            if last_close > sma5 or last_close > ema8:
                return False if is_btc else True

            if last_close > max(highs[-3:]):
                return False

        # SHORT reversal
        if direction == "short":

            if closes[-1] < closes[-2] < closes[-3]:
                return False

            if last_close < sma5 or last_close < ema8:
                return False if is_btc else True

            if last_close < min(lows[-3:]):
                return False

        return True

    # ==========================================================
    # HELPERS
    # ==========================================================

    def _effective_atr(self, regime: Dict) -> float:
        atr_main = float(regime.get("atr_percentile", 0.0))
        atr_short = float(regime.get("atr_short_percentile", atr_main))
        atr_long = float(regime.get("atr_long_percentile", atr_main))
        atr_eff = 0.5 * atr_short + 0.5 * atr_long
        return max(0.0, min(atr_eff, 1.0))
