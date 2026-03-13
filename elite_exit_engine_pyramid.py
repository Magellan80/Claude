# elite_exit_engine_pyramid.py
# V32.6 — Partial @ 0.7R + Pyramid start @ 0.5R + STRONG_TREND only + ATR‑adaptive

from typing import Dict, Optional


class EliteExitEnginePyramid:

    def __init__(self):
        self.time_exit_range  = 25
        self.time_exit_trend  = 60

        # Ранний BE
        self.early_be_r       = 0.7

        # PARTIAL теперь раньше: 0.7R
        self.partial_r        = 0.7

        # Второй partial остаётся прежним
        self.second_partial_r = 2.0

        # Пирамидинг после partial
        self.max_pyramids     = 3

        # Первый уровень пирамидинга теперь 0.5R
        self.pyramid_start_r  = 0.5

        # Шаг между добавлениями оставляем прежним
        self.pyramid_step_r   = 0.7

        self.add_risk_pct     = 0.007
        self.min_atr          = 1e-8

    # ==========================================================
    # PUBLIC ENTRY
    # ==========================================================

    def manage_position(
        self,
        position:       Dict,
        current_price:  float,
        atr:            float,
        regime:         str,
        bar_index:      int,
        current_candle: Optional[Dict] = None
    ) -> Dict:

        if position["status"] == "CLOSED":
            return position

        entry     = position["entry"]
        sl        = position["sl"]
        direction = position["direction"]

        atr = max(atr, self.min_atr)
        risk = abs(entry - sl)
        if risk <= 0:
            return position

        r_multiple = self._r_multiple(direction, entry, sl, current_price)

        # worst price
        if current_candle:
            worst_price = (
                float(current_candle["low"]) if direction == "long"
                else float(current_candle["high"])
            )
        else:
            worst_price = current_price

        # STOP LOSS (с определением BE)
        if self._stop_hit(direction, worst_price, sl):
            position["status"]     = "CLOSED"
            position["exit_price"] = sl

            entry = position["entry"]

            # Определяем BE-стоп
            is_be = False

            # 1) Early BE был активирован
            if position.get("early_be_done"):
                is_be = True

            # 2) Partial BE был активирован
            if position.get("partial_taken"):
                is_be = True

            # 3) Стоп реально стоит в плюсе
            if direction == "long" and sl >= entry:
                is_be = True
            if direction == "short" and sl <= entry:
                is_be = True

            if is_be:
                position["reason"] = "breakeven_stop"
            else:
                position["reason"] = "stop_loss"

            return position

        # EARLY BE with fixed buffer 0.12%
        if (
            not position["partial_taken"]
            and r_multiple >= self.early_be_r
            and not position.get("early_be_done", False)
        ):
            BE_BUFFER = 0.0012  # 0.12%

            if direction == "long":
                new_sl = entry * (1 + BE_BUFFER)
                position["sl"] = max(position["sl"], new_sl)
            else:
                new_sl = entry * (1 - BE_BUFFER)
                position["sl"] = min(position["sl"], new_sl)

            position["early_be_done"] = True
            position["reason"] = "early_be"

        # PARTIAL @ 0.7R
        if not position["partial_taken"] and r_multiple >= self.partial_r:
            position["partial_taken"]  = True
            position["partial_price"]  = current_price

            buffer = 0.10 * atr
            if direction == "long":
                position["sl"] = max(position["sl"], entry + buffer)
            else:
                position["sl"] = min(position["sl"], entry - buffer)

            position["reason"] = "partial_be"

        # SECOND PARTIAL @ 2R
        if (
            position["partial_taken"]
            and not position.get("second_partial")
            and regime == "STRONG_TREND"
            and r_multiple >= self.second_partial_r
        ):
            position["second_partial"]       = True
            position["second_partial_price"] = current_price

            if direction == "long":
                position["sl"] = max(position["sl"], entry + 0.7 * risk)
            else:
                position["sl"] = min(position["sl"], entry - 0.7 * risk)

        # PYRAMIDING
        self._handle_pyramiding(position, r_multiple, regime, current_price, atr)

        # TRAILING
        allow_trail = (regime == "STRONG_TREND") or position["partial_taken"]

        if allow_trail:
            new_sl = self._adaptive_trailing(direction, current_price, atr, regime, position)
            old_sl = position["sl"]

            if direction == "long":
                position["sl"] = max(old_sl, new_sl)
            else:
                position["sl"] = min(old_sl, new_sl)

            if self._stop_hit(direction, current_price, position["sl"]):
                position["status"]     = "CLOSED"
                position["exit_price"] = position["sl"]
                position["reason"]     = "trailing_stop"
                return position

        return position

    # ==========================================================
    # PYRAMIDING AFTER PARTIAL (STRONG_TREND only)
    # ==========================================================

    def _handle_pyramiding(
        self,
        position:      Dict,
        r_multiple:    float,
        regime:        str,
        current_price: float,
        atr:           float,
    ) -> None:

        if not position.get("partial_taken"):
            return

        if regime != "STRONG_TREND":
            return

        if "pyramid_count" not in position:
            position["pyramid_count"] = 0

        if position["pyramid_count"] >= self.max_pyramids:
            return

        # Новый старт: 0.5R
        next_level = self.pyramid_start_r + position["pyramid_count"] * self.pyramid_step_r

        if r_multiple < next_level:
            return

        risk = abs(position["entry"] - position["sl"])
        if risk <= 0:
            return

        atr_r = atr / risk

        if atr_r < 0.6:
            add_risk_pct = 0.005
        elif atr_r < 1.2:
            add_risk_pct = 0.007
        else:
            add_risk_pct = 0.010

        base_notional = position["entry"] * position["size"]
        add_notional  = base_notional * add_risk_pct
        add_size      = add_notional / current_price

        position["pyramid_signal"] = {
            "add_size":      add_size,
            "add_price":     current_price,
            "level_r":       next_level,
            "pyramid_index": position["pyramid_count"] + 1,
        }

        position["pyramid_count"] += 1
        position["reason"] = "pyramid_add"

    # ==========================================================
    # R MULTIPLE
    # ==========================================================

    def _r_multiple(self, direction: str, entry: float, sl: float, price: float) -> float:
        risk = abs(entry - sl)
        if risk <= 0:
            return 0.0
        return (price - entry) / risk if direction == "long" else (entry - price) / risk

    # ==========================================================
    # STOP HIT
    # ==========================================================

    def _stop_hit(self, direction: str, price: float, sl: float) -> bool:
        return price <= sl if direction == "long" else price >= sl

    # ==========================================================
    # ADAPTIVE TRAILING
    # ==========================================================

    def _adaptive_trailing(
        self,
        direction: str,
        price:     float,
        atr:       float,
        regime:    str,
        position:  Dict
    ) -> float:

        if regime == "STRONG_TREND":
            trail = 0.55 * atr
        else:
            trail = 1.20 * atr

        if position.get("second_partial"):
            trail *= 0.70

        swing_offset = 0.35 * atr

        return min(price - trail, price - swing_offset) if direction == "long" else max(price + trail, price + swing_offset)
