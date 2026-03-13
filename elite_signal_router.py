# elite_signal_router.py
# V32.1 ELITE — Trend-Friendly Router (BTC Mixed Regime + Local Impulse Filter)

from typing import Optional, Dict


class EliteSignalRouter:

    def __init__(self):
        self.min_alignment = 0.45
        self.min_trend_conf = 0.45

        self.reversal_allowed = [
            "RANGE", "EXHAUSTION", "LOW_VOL_RANGE", "COMPRESSION"
        ]

    # ==========================================================
    # PUBLIC ENTRY
    # ==========================================================

    def route(self, trend_signal, reversal_signal, regime, htf, symbol: str = "BTCUSDT"):

        regime_type = str(regime.get("regime", "RANGE")).upper()
        htf_regime = str(htf.get("htf_regime", "HTF_RANGE")).upper()
        alignment = float(htf.get("alignment_score", 0.0))
        exhausted = bool(htf.get("exhausted", False))
        trend_conf = float(regime.get("trend_confidence", 0.0))

        # ------------------------------------------------------
        # BTC‑режим: строгая фильтрация входов
        # ------------------------------------------------------
        if symbol == "BTCUSDT":
            return self._route_btc(
                trend_signal, reversal_signal,
                regime_type, htf_regime,
                alignment, exhausted, trend_conf,
                structure=regime.get("structure_context", None)
            )

        # ------------------------------------------------------
        # Обычный режим (DOGE / high-vol)
        # ------------------------------------------------------
        if not trend_signal and not reversal_signal:
            return None

        if trend_signal and not reversal_signal:
            if regime_type == "COMPRESSION":
                return trend_signal
            return self._validate_trend(trend_signal, regime_type, htf_regime, alignment, trend_conf)

        if reversal_signal and not trend_signal:
            return self._validate_reversal(reversal_signal, regime_type, exhausted)

        return self._resolve_conflict(
            trend_signal, reversal_signal,
            regime_type, htf_regime, alignment, exhausted, trend_conf
        )

    # ==========================================================
    # BTC ROUTING LOGIC (V32.1)
    # ==========================================================

    def _route_btc(self, trend_signal, reversal_signal, regime_type, htf_regime, alignment, exhausted, trend_conf, structure):

        # Нет сигналов
        if not trend_signal and not reversal_signal:
            return None

        # ======================================================
        # LOCAL IMPULSE FILTER (BTC-only, Router-level)
        # ======================================================
        if structure and "recent_candles" in structure:
            candles = structure["recent_candles"]
            if len(candles) >= 5:

                closes = [c["close"] for c in candles[-5:]]
                highs  = [c["high"]  for c in candles[-5:]]
                lows   = [c["low"]   for c in candles[-5:]]

                last_close = closes[-1]

                sma5 = sum(closes[-5:]) / 5
                ema8 = closes[-1]
                for c in closes[-8:]:
                    ema8 = ema8 * 0.7 + c * 0.3

                # --- TREND LONG против импульса ---
                if trend_signal and trend_signal["signal"] == "long":
                    if closes[-1] < closes[-2] < closes[-3]:
                        trend_signal = None
                    if last_close < sma5 or last_close < ema8:
                        trend_signal = None
                    if last_close < min(lows[-3:]):
                        trend_signal = None

                # --- TREND SHORT против импульса ---
                if trend_signal and trend_signal["signal"] == "short":
                    if closes[-1] > closes[-2] > closes[-3]:
                        trend_signal = None
                    if last_close > sma5 or last_close > ema8:
                        trend_signal = None
                    if last_close > max(highs[-3:]):
                        trend_signal = None

                # --- REVERSAL LONG против импульса ---
                if reversal_signal and reversal_signal["signal"] == "long":
                    if closes[-1] > closes[-2] > closes[-3]:
                        reversal_signal = None
                    if last_close > sma5 or last_close > ema8:
                        reversal_signal = None
                    if last_close > max(highs[-3:]):
                        reversal_signal = None

                # --- REVERSAL SHORT против импульса ---
                if reversal_signal and reversal_signal["signal"] == "short":
                    if closes[-1] < closes[-2] < closes[-3]:
                        reversal_signal = None
                    if last_close < sma5 or last_close < ema8:
                        reversal_signal = None
                    if last_close < min(lows[-3:]):
                        reversal_signal = None

        # --------------------------------------------------
        # BTC: TREND‑входы только при сильном HTF‑контексте
        # --------------------------------------------------
        if trend_signal:
            if trend_signal["quality"] < 0.60:
                trend_signal = None
            if alignment < 0.55:
                trend_signal = None
            if regime_type not in ["EARLY_TREND", "STRONG_TREND", "EXPANSION", "HTF_TREND"]:
                trend_signal = None

        # --------------------------------------------------
        # BTC: REVERSAL‑входы только в боковике/low-vol
        # --------------------------------------------------
        if reversal_signal:
            if reversal_signal["quality"] < 0.60:
                reversal_signal = None
            if regime_type not in ["RANGE", "LOW_VOL_RANGE", "EXHAUSTION", "COMPRESSION"]:
                reversal_signal = None
            if not exhausted:
                reversal_signal = None

        # --------------------------------------------------
        # Если остался только один сигнал — берём его
        # --------------------------------------------------
        if trend_signal and not reversal_signal:
            return trend_signal
        if reversal_signal and not trend_signal:
            return reversal_signal

        # --------------------------------------------------
        # Конфликт: TREND vs REVERSAL
        # --------------------------------------------------

        # В сильном тренде — только TREND
        if regime_type == "STRONG_TREND":
            if alignment >= 0.60:
                return trend_signal
            return None

        # В RANGE / LOW_VOL_RANGE — только REVERSAL
        if regime_type in ["RANGE", "LOW_VOL_RANGE"]:
            return reversal_signal

        # В EXHAUSTION — REVERSAL
        if regime_type == "EXHAUSTION":
            return reversal_signal

        # В COMPRESSION — выбираем более качественный
        if regime_type == "COMPRESSION":
            return self._higher_quality(trend_signal, reversal_signal)

        # В EXPANSION — TREND при хорошем alignment
        if regime_type == "EXPANSION":
            if alignment >= 0.60:
                return trend_signal
            if exhausted:
                return reversal_signal
            return self._higher_quality(trend_signal, reversal_signal)

        # В EARLY_TREND — TREND при хорошем alignment
        if regime_type == "EARLY_TREND":
            if alignment >= 0.60:
                return trend_signal
            return self._higher_quality(trend_signal, reversal_signal)

        # fallback
        return self._higher_quality(trend_signal, reversal_signal)

    # ==========================================================
    # ORIGINAL VALIDATION (DOGE / high-vol)
    # ==========================================================

    def _validate_trend(self, trend_signal, regime_type, htf_regime, alignment, trend_conf):

        if alignment < self.min_alignment:
            return None

        if regime_type == "CHAOS":
            return None

        return trend_signal

    def _validate_reversal(self, reversal_signal, regime_type, exhausted):

        if regime_type not in self.reversal_allowed:
            return None

        return reversal_signal

    def _resolve_conflict(self, trend_signal, reversal_signal, regime_type, htf_regime, alignment, exhausted, trend_conf):

        if regime_type == "CHAOS":
            return reversal_signal

        if regime_type == "STRONG_TREND":
            if alignment >= self.min_alignment:
                return trend_signal
            return None

        if regime_type in ["RANGE", "LOW_VOL_RANGE"]:
            return reversal_signal

        if regime_type == "EXHAUSTION":
            return reversal_signal

        if regime_type == "COMPRESSION":
            return self._higher_quality(trend_signal, reversal_signal)

        if regime_type == "EXPANSION":
            if alignment >= self.min_alignment:
                return trend_signal
            if exhausted:
                return reversal_signal
            return self._higher_quality(trend_signal, reversal_signal)

        if regime_type == "EARLY_TREND":
            if alignment >= self.min_alignment:
                return trend_signal
            return self._higher_quality(trend_signal, reversal_signal)

        return self._higher_quality(trend_signal, reversal_signal)

    # ==========================================================
    # QUALITY COMPARATOR
    # ==========================================================

    def _higher_quality(self, s1, s2):
        if not s1 and not s2:
            return None
        if s1 and not s2:
            return s1
        if s2 and not s1:
            return s2
        if s1["quality"] > s2["quality"]:
            return s1
        if s2["quality"] > s1["quality"]:
            return s2
        return None
