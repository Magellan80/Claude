# elite_trend_engine.py
# V33 ELITE — Trend Engine Adaptive (Volatility & Symbol Aware)

from typing import Dict, Optional


class EliteTrendEngine:

    def __init__(self):
        # Базовые пороги (fallback, если нет адаптации)
        self.base_min_quality = 0.50
        self.base_min_clarity = 0.35
        self.base_min_impulse = 0.025
        self.base_min_alignment = 0.40
        self.base_min_signed_strength = 0.006

    # ==========================================================
    # PUBLIC ENTRY
    # ==========================================================

    def evaluate(self, structure: Dict, regime: Dict, htf: Dict, symbol: str = "BTCUSDT") -> Optional[Dict]:

        if not structure or not regime or not htf:
            return None

        # Адаптивные пороги под волатильность и символ
        min_clarity, min_impulse, min_alignment, min_signed_strength = \
            self._adaptive_thresholds(structure, regime, htf, symbol)

        direction = self._direction(structure, regime, htf, min_alignment, min_signed_strength)
        if not direction:
            return None

        # фильтры качества структуры
        if float(structure.get("clarity_index", 0.0)) < min_clarity:
            return None

        if float(structure.get("impulse_strength", 0.0)) < min_impulse:
            return None

        quality = self._quality_score(structure, regime, htf, symbol)
        if quality < self.base_min_quality:
            return None

        # ==========================================================
        # LOCAL IMPULSE FILTER (адаптивный, не только BTC)
        # ==========================================================
        if not self._local_impulse_ok(structure, direction, symbol):
            return None

        return {
            "signal": direction,
            "quality": quality,
            "type": "trend"
        }

    # ==========================================================
    # ADAPTIVE THRESHOLDS
    # ==========================================================

    def _adaptive_thresholds(self, structure: Dict, regime: Dict, htf: Dict, symbol: str):
        atr_p = float(regime.get("atr_percentile", 0.5))

        # Базовые
        min_clarity = self.base_min_clarity
        min_impulse = self.base_min_impulse
        min_alignment = self.base_min_alignment
        min_signed_strength = self.base_min_signed_strength

        # Символьные поправки (BTC чуть жёстче, DOGE/SOL/OP мягче)
        symbol_upper = symbol.upper()
        is_btc = symbol_upper.startswith("BTC")
        is_high_vol = symbol_upper.startswith(("DOGE", "SOL", "OP", "ARB", "AVAX"))

        # Волатильность + символ
        if atr_p > 0.60:
            # High-vol режим
            min_clarity = 0.30
            min_impulse = 0.020
            min_alignment = 0.30
            min_signed_strength = 0.004
            if is_btc:
                # BTC в high-vol всё равно чуть жёстче
                min_alignment = 0.40
                min_signed_strength = 0.006

        elif atr_p > 0.30:
            # Medium-vol
            min_clarity = 0.35
            min_impulse = 0.025
            min_alignment = 0.40
            min_signed_strength = 0.006
            if is_btc:
                min_alignment = 0.45
                min_signed_strength = 0.008

        else:
            # Low-vol (BTC, BNB и т.п.)
            min_clarity = 0.40
            min_impulse = 0.030
            min_alignment = 0.50
            min_signed_strength = 0.010
            if is_high_vol:
                # Если вдруг high-vol монета попала в low-vol период
                min_alignment = 0.45
                min_signed_strength = 0.008

        return min_clarity, min_impulse, min_alignment, min_signed_strength

    # ==========================================================
    # TREND DIRECTION (Adaptive)
    # ==========================================================

    def _direction(
        self,
        structure: Dict,
        regime: Dict,
        htf: Dict,
        min_alignment: float,
        min_signed_strength: float
    ) -> Optional[str]:

        regime_name = str(regime.get("regime", "RANGE")).upper()
        bias = str(htf.get("bias", "neutral")).lower()
        alignment = float(htf.get("alignment_score", 0.5))
        signed_strength = float(htf.get("signed_trend_strength", 0.0))
        local_structure = structure.get("structure", "neutral")

        # 1. Разрешённые режимы
        allowed = [
            "TREND",
            "EARLY_TREND",
            "STRONG_TREND",
            "EXPANSION",
            "HTF_TREND",
            "HTF_WEAK_TREND",
            "COMPRESSION",
        ]
        if regime_name not in allowed:
            return None

        # 2. COMPRESSION — только сильные тренды
        if regime_name == "COMPRESSION":
            if abs(signed_strength) < max(0.012, min_signed_strength * 1.5):
                return None
            if alignment < max(0.55, min_alignment + 0.10):
                return None

        # 3. Минимальная сила HTF тренда
        if abs(signed_strength) < min_signed_strength:
            return None

        # 4. Минимальное согласование HTF
        if alignment < min_alignment:
            return None

        # 5. Neutral-structure → только при очень сильном HTF тренде
        if (
            local_structure == "neutral"
            and abs(signed_strength) > (min_signed_strength * 3.5)
            and alignment > (min_alignment + 0.20)
        ):
            if bias == "bullish":
                return "long"
            if bias == "bearish":
                return "short"
            return None

        # 6. Классическая логика направления
        if local_structure == "bullish" and bias == "bullish":
            return "long"

        if local_structure == "bearish" and bias == "bearish":
            return "short"

        return None

    # ==========================================================
    # QUALITY SCORE (Adaptive)
    # ==========================================================

    def _quality_score(self, structure: Dict, regime: Dict, htf: Dict, symbol: str) -> float:

        clarity = float(structure.get("clarity_index", 0.0))
        impulse = float(structure.get("impulse_strength", 0.0))
        alignment = float(htf.get("alignment_score", 0.5))
        signed_strength = abs(float(htf.get("signed_trend_strength", 0.0)))
        atr_p = float(regime.get("atr_percentile", 0.5))

        score = 0.0

        # 1. Чистота структуры
        score += clarity * 0.30

        # 2. Импульс (волатильность-нормированный)
        # high-vol монеты получают чуть меньший вес за тот же impulse
        vol_factor = 1.0
        symbol_upper = symbol.upper()
        if symbol_upper.startswith(("DOGE", "SOL", "OP", "ARB", "AVAX")):
            vol_factor = 0.85
        impulse_norm = min(impulse * vol_factor / 2.0, 1.0)
        score += impulse_norm * 0.25

        # 3. HTF alignment
        score += alignment * 0.22

        # 4. Сила HTF тренда
        if signed_strength > 0.030:
            score += 0.20
        elif signed_strength > 0.018:
            score += 0.14
        elif signed_strength > 0.010:
            score += 0.09
        else:
            score += 0.04

        # 5. Анти‑шумовой штраф (чуть мягче)
        noise_penalty = max(0.0, 0.25 - clarity)
        score -= noise_penalty * 0.15

        # 6. Бонус за благоприятный режим
        regime_name = str(regime.get("regime", "RANGE")).upper()
        if regime_name in ("TREND", "STRONG_TREND", "EXPANSION", "HTF_TREND"):
            score += 0.05
        elif regime_name in ("EARLY_TREND", "HTF_WEAK_TREND", "COMPRESSION"):
            score += 0.03

        return max(0.0, min(score, 1.0))

    # ==========================================================
    # LOCAL IMPULSE FILTER (Adaptive, all symbols)
    # ==========================================================

    def _local_impulse_ok(self, structure: Dict, direction: str, symbol: str) -> bool:

        candles = structure.get("recent_candles", [])
        if len(candles) < 5:
            return True

        closes = [c["close"] for c in candles[-5:]]
        highs  = [c["high"]  for c in candles[-5:]]
        lows   = [c["low"]   for c in candles[-5:]]

        last_close = closes[-1]

        # SMA(5)
        sma5 = sum(closes[-5:]) / 5

        # EMA(8) (простая экспоненциальная аппроксимация)
        ema8 = closes[-1]
        for c in closes[-5:]:
            ema8 = ema8 * 0.7 + c * 0.3

        # Символьная чувствительность: BTC строже, high-vol чуть мягче
        symbol_upper = symbol.upper()
        is_btc = symbol_upper.startswith("BTC")
        is_high_vol = symbol_upper.startswith(("DOGE", "SOL", "OP", "ARB", "AVAX"))

        # Минимальное количество баров для паттерна
        if len(closes) < 3:
            return True

        # --- LONG против локального импульса ---
        if direction == "long":

            # 3 красных бара подряд
            if closes[-1] < closes[-2] < closes[-3]:
                return False

            # цена ниже SMA/EMA — для BTC строже
            if last_close < sma5 or last_close < ema8:
                if is_btc or not is_high_vol:
                    return False

            # пробой минимума последних 3 баров
            if last_close < min(lows[-3:]):
                return False

        # --- SHORT против локального импульса ---
        if direction == "short":

            # 3 зелёных бара подряд
            if closes[-1] > closes[-2] > closes[-3]:
                return False

            # цена выше SMA/EMA — для BTC строже
            if last_close > sma5 or last_close > ema8:
                if is_btc or not is_high_vol:
                    return False

            # пробой максимума последних 3 баров
            if last_close > max(highs[-3:]):
                return False

        return True
