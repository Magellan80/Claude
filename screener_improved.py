import time
import asyncio
import aiohttp
from typing import Any, Dict, Optional, List, Tuple
from io import BytesIO
import traceback
import pandas as pd
import mplfinance as mpf
from aiogram.types import BufferedInputFile
from functools import lru_cache
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict
import json

from config import get_current_mode, load_settings
from data_layer import (
    fetch_tickers,
    fetch_klines,
    fetch_open_interest,
    fetch_funding_rate,
    fetch_liquidations,
    fetch_recent_trades,
    fetch_orderbook,
)
from liquidity_map import build_liquidity_map

from context import (
    compute_trend_score,
    compute_risk_score,
    funding_bias,
    interpret_liquidations,
    analyze_flow_from_trades,
    analyze_delta_from_trades,
    format_funding_text,
    format_liq_text,
    format_flow_text,
    format_delta_text,
)
from detectors import (
    detect_big_pump,
    detect_big_dump,
    detect_pump_reversal,
    adjust_rating_with_context,
    detector,
)
from microstructure import (
    build_price_buckets,
    analyze_microstructure,
)
from htf_structure import compute_htf_structure, detect_swings
from footprint import compute_footprint_zones

from smart_filters_v3 import apply_smartfilters_v3
from symbol_memory import (
    update_symbol_memory,
    get_symbol_memory,
    get_symbol_state,
    set_symbol_state,
    clear_symbol_state,
)

# ============================================================================
# КОНСТАНТЫ И КОНФИГУРАЦИЯ
# ============================================================================

SYMBOL_COOLDOWN = 300
MAX_CONCURRENT_REQUESTS = 10  # Лимит параллельных запросов к API

# Кэш для данных
_KLINES_CACHE = {}
_CACHE_TTL = 60  # секунд

_last_signal_ts = {}

_BTC_CTX_CACHE = {
    "ts": 0.0,
    "factor": 1.0,
    "regime": "neutral",
}

# ============================================================================
# НОВАЯ СИСТЕМА ОТСЛЕЖИВАНИЯ ПРОИЗВОДИТЕЛЬНОСТИ
# ============================================================================

@dataclass
class SignalPerformance:
    """Отслеживание результатов сигналов"""
    signal_id: str
    symbol: str
    signal_type: str
    entry_price: float
    rating: int
    confidence: float
    timestamp: float
    outcome_checked: bool = False
    outcome_success: Optional[bool] = None
    exit_price: Optional[float] = None
    pnl_percent: Optional[float] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


class PerformanceTracker:
    """Трекер производительности сигналов"""
    
    def __init__(self, db_path: str = "signal_performance.json"):
        self.db_path = db_path
        self.signals: Dict[str, SignalPerformance] = {}
        self.stats = {
            'total_signals': 0,
            'checked_signals': 0,
            'successful_signals': 0,
            'failed_signals': 0,
            'pump_win_rate': 0.0,
            'dump_win_rate': 0.0,
            'reversal_win_rate': 0.0,
            'avg_pnl': 0.0,
            'avg_rating_vs_outcome': {},
        }
        self._load_from_disk()
    
    def _load_from_disk(self):
        """Загрузка данных с диска"""
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
                self.signals = {k: SignalPerformance(**v) for k, v in data.get('signals', {}).items()}
                self.stats = data.get('stats', self.stats)
        except FileNotFoundError:
            pass
    
    def _save_to_disk(self):
        """Сохранение данных на диск"""
        data = {
            'signals': {k: v.to_dict() for k, v in self.signals.items()},
            'stats': self.stats
        }
        with open(self.db_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_signal(self, signal: dict) -> str:
        """Добавление нового сигнала для отслеживания"""
        signal_id = f"{signal['symbol']}_{int(time.time())}"
        
        perf = SignalPerformance(
            signal_id=signal_id,
            symbol=signal['symbol'],
            signal_type=signal['type'],
            entry_price=signal['price'],
            rating=signal['rating'],
            confidence=signal.get('confidence', 0.0),
            timestamp=time.time()
        )
        
        self.signals[signal_id] = perf
        self.stats['total_signals'] += 1
        self._save_to_disk()
        
        return signal_id
    
    async def check_signal_outcome(self, signal_id: str, session: aiohttp.ClientSession, 
                                   check_minutes: int = 15):
        """Проверка результата сигнала через N минут"""
        if signal_id not in self.signals:
            return
        
        signal = self.signals[signal_id]
        if signal.outcome_checked:
            return
        
        # Ждём указанное время
        elapsed = time.time() - signal.timestamp
        if elapsed < check_minutes * 60:
            return
        
        try:
            # Получаем текущую цену
            klines = await fetch_klines(session, signal.symbol, interval="1", limit=1)
            if not klines:
                return
            
            current_price = float(klines[0][4])
            signal.exit_price = current_price
            
            # Определяем успешность
            pnl_percent = ((current_price - signal.entry_price) / signal.entry_price) * 100
            signal.pnl_percent = pnl_percent
            
            if "PUMP" in signal.signal_type or "Dump → Pump" in signal.signal_type:
                signal.outcome_success = pnl_percent > 0.5  # Минимум 0.5% прибыли
            elif "DUMP" in signal.signal_type or "Pump → Dump" in signal.signal_type:
                signal.outcome_success = pnl_percent < -0.5
            else:
                signal.outcome_success = abs(pnl_percent) > 0.5
            
            signal.outcome_checked = True
            
            # Обновляем статистику
            self._update_stats()
            self._save_to_disk()
            
        except Exception as e:
            log_error(e)
    
    def _update_stats(self):
        """Обновление статистики"""
        checked = [s for s in self.signals.values() if s.outcome_checked]
        if not checked:
            return
        
        self.stats['checked_signals'] = len(checked)
        self.stats['successful_signals'] = sum(1 for s in checked if s.outcome_success)
        self.stats['failed_signals'] = sum(1 for s in checked if not s.outcome_success)
        
        # Win rates по типам
        pump_signals = [s for s in checked if "PUMP" in s.signal_type]
        dump_signals = [s for s in checked if "DUMP" in s.signal_type]
        reversal_signals = [s for s in checked if "REVERSAL" in s.signal_type]
        
        if pump_signals:
            self.stats['pump_win_rate'] = sum(1 for s in pump_signals if s.outcome_success) / len(pump_signals)
        if dump_signals:
            self.stats['dump_win_rate'] = sum(1 for s in dump_signals if s.outcome_success) / len(dump_signals)
        if reversal_signals:
            self.stats['reversal_win_rate'] = sum(1 for s in reversal_signals if s.outcome_success) / len(reversal_signals)
        
        # Средний PnL
        pnls = [s.pnl_percent for s in checked if s.pnl_percent is not None]
        if pnls:
            self.stats['avg_pnl'] = sum(pnls) / len(pnls)
        
        # Корреляция рейтинга с результатом
        rating_outcomes = defaultdict(list)
        for s in checked:
            rating_bucket = (s.rating // 10) * 10  # Группируем по 10
            rating_outcomes[rating_bucket].append(1 if s.outcome_success else 0)
        
        for rating, outcomes in rating_outcomes.items():
            self.stats['avg_rating_vs_outcome'][str(rating)] = sum(outcomes) / len(outcomes)
    
    def get_stats_text(self) -> str:
        """Форматированная статистика"""
        return (
            f"📊 Статистика сигналов:\n"
            f"Всего: {self.stats['total_signals']} | Проверено: {self.stats['checked_signals']}\n"
            f"Успешных: {self.stats['successful_signals']} | Неудачных: {self.stats['failed_signals']}\n"
            f"Win Rate: PUMP={self.stats['pump_win_rate']:.1%} | DUMP={self.stats['dump_win_rate']:.1%} | "
            f"REVERSAL={self.stats['reversal_win_rate']:.1%}\n"
            f"Средний PnL: {self.stats['avg_pnl']:.2f}%\n"
        )
    
    def should_alert_degradation(self, threshold: float = 0.45) -> bool:
        """Проверка деградации модели"""
        if self.stats['checked_signals'] < 20:  # Минимум данных для выводов
            return False
        
        win_rate = self.stats['successful_signals'] / self.stats['checked_signals']
        return win_rate < threshold


# Глобальный трекер производительности
performance_tracker = PerformanceTracker()

# ============================================================================
# АДАПТИВНЫЙ MIN SCORE
# ============================================================================

def get_adaptive_min_score(btc_regime: str, global_vol: float = 1.0, base_score: int = 60) -> int:
    """
    Динамическая калибровка минимального порога сигнала
    
    Args:
        btc_regime: Режим BTC (trending/ranging/high_vol)
        global_vol: Глобальная волатильность (1.0 = нормальная)
        base_score: Базовый порог
    
    Returns:
        Адаптированный минимальный score
    """
    adjusted = base_score
    
    # В высокой волатильности — строже
    if btc_regime == "high_vol":
        adjusted += 10
    # В спокойном рынке — мягче
    elif btc_regime == "ranging":
        adjusted -= 5
    # В тренде — немного строже для реверсалов
    elif btc_regime == "trending":
        adjusted += 3
    
    # Дополнительная коррекция по волатильности
    if global_vol > 1.5:
        adjusted += 5
    elif global_vol < 0.7:
        adjusted -= 3
    
    return max(40, min(adjusted, 80))  # Ограничиваем диапазон


# ============================================================================
# POSITION SIZING И RISK MANAGEMENT
# ============================================================================

def calculate_position_size(rating: int, confidence: float, atr: float, 
                           risk_score: int, account_size: float = 1000.0,
                           risk_per_trade: float = 0.02) -> dict:
    """
    Расчёт размера позиции и уровней SL/TP
    
    Args:
        rating: Рейтинг сигнала (0-100)
        confidence: Уверенность (0-1)
        atr: Average True Range для волатильности
        risk_score: Оценка риска
        account_size: Размер счёта в USDT
        risk_per_trade: Риск на сделку (0.02 = 2%)
    
    Returns:
        dict с размером позиции и уровнями
    """
    # Базовый риск
    base_risk = account_size * risk_per_trade
    
    # Корректировка по рейтингу и уверенности
    quality_multiplier = (rating / 100) * confidence
    adjusted_risk = base_risk * quality_multiplier
    
    # Корректировка по risk_score
    if risk_score > 7:
        adjusted_risk *= 0.7  # Снижаем риск в опасных условиях
    elif risk_score < 3:
        adjusted_risk *= 1.2  # Можно чуть больше в безопасных
    
    # Stop Loss на основе ATR
    sl_distance = atr * 1.5  # 1.5 ATR
    
    # Take Profit - соотношение 1:2 или 1:3
    tp_distance_conservative = atr * 3.0
    tp_distance_aggressive = atr * 4.5
    
    # Размер позиции = риск / расстояние до SL
    position_size_usdt = adjusted_risk / (sl_distance / 100)  # Примерный расчёт
    
    return {
        'position_size_usdt': round(position_size_usdt, 2),
        'sl_distance_percent': round((sl_distance / 100) * 100, 2),
        'tp_conservative_percent': round((tp_distance_conservative / 100) * 100, 2),
        'tp_aggressive_percent': round((tp_distance_aggressive / 100) * 100, 2),
        'risk_amount_usdt': round(adjusted_risk, 2),
        'quality_score': round(quality_multiplier * 100, 1)
    }


def add_sl_tp_to_signal(signal: dict, current_price: float, atr: float) -> dict:
    """Добавление уровней SL/TP к сигналу"""
    
    is_long = any(x in signal['type'] for x in ["PUMP", "Dump → Pump"])
    
    if is_long:
        signal['stop_loss'] = round(current_price - (atr * 1.5), 4)
        signal['take_profit_1'] = round(current_price + (atr * 3.0), 4)
        signal['take_profit_2'] = round(current_price + (atr * 4.5), 4)
    else:
        signal['stop_loss'] = round(current_price + (atr * 1.5), 4)
        signal['take_profit_1'] = round(current_price - (atr * 3.0), 4)
        signal['take_profit_2'] = round(current_price - (atr * 4.5), 4)
    
    # Расчёт размера позиции
    position_info = calculate_position_size(
        rating=signal['rating'],
        confidence=signal.get('confidence', 0.5),
        atr=atr,
        risk_score=signal['risk_score']
    )
    
    signal['position_sizing'] = position_info
    
    return signal


# ============================================================================
# VOLUME PROFILE ANALYSIS
# ============================================================================

def compute_volume_profile(klines: list, num_levels: int = 20) -> dict:
    """
    Анализ профиля объёма для определения POC и значимых уровней
    
    Args:
        klines: Массив свечей
        num_levels: Количество уровней цены для группировки
    
    Returns:
        dict с POC, VPOC и уровнями поддержки/сопротивления
    """
    if not klines or len(klines) < 10:
        return {'poc': None, 'vpoc': None, 'high_volume_levels': []}
    
    # Извлекаем данные
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]
    
    price_min = min(lows)
    price_max = max(highs)
    price_range = price_max - price_min
    
    if price_range == 0:
        return {'poc': None, 'vpoc': None, 'high_volume_levels': []}
    
    # Создаём уровни цен
    level_size = price_range / num_levels
    volume_by_level = defaultdict(float)
    
    for i in range(len(klines)):
        high = highs[i]
        low = lows[i]
        vol = volumes[i]
        
        # Распределяем объём по уровням, которые касается свеча
        start_level = int((low - price_min) / level_size)
        end_level = int((high - price_min) / level_size)
        
        for level in range(start_level, end_level + 1):
            if 0 <= level < num_levels:
                volume_by_level[level] += vol / (end_level - start_level + 1)
    
    # Находим POC (Point of Control) - уровень с максимальным объёмом
    if volume_by_level:
        poc_level = max(volume_by_level.items(), key=lambda x: x[1])[0]
        poc_price = price_min + (poc_level * level_size) + (level_size / 2)
        
        # VPOC - Value Point of Control (средневзвешенная цена по объёму)
        total_volume = sum(volume_by_level.values())
        weighted_sum = sum((price_min + (lvl * level_size) + (level_size / 2)) * vol 
                          for lvl, vol in volume_by_level.items())
        vpoc_price = weighted_sum / total_volume if total_volume > 0 else poc_price
        
        # Находим уровни с высоким объёмом (топ 20%)
        sorted_levels = sorted(volume_by_level.items(), key=lambda x: x[1], reverse=True)
        top_levels_count = max(3, num_levels // 5)
        high_volume_levels = [
            round(price_min + (lvl * level_size) + (level_size / 2), 4)
            for lvl, vol in sorted_levels[:top_levels_count]
        ]
        
        return {
            'poc': round(poc_price, 4),
            'vpoc': round(vpoc_price, 4),
            'high_volume_levels': high_volume_levels,
            'volume_distribution': dict(volume_by_level)
        }
    
    return {'poc': None, 'vpoc': None, 'high_volume_levels': []}


# ============================================================================
# УЛУЧШЕННОЕ КЭШИРОВАНИЕ
# ============================================================================

def get_cache_key(symbol: str, interval: str, limit: int) -> str:
    """Генерация ключа для кэша"""
    return f"{symbol}_{interval}_{limit}"


async def fetch_klines_cached(session: aiohttp.ClientSession, symbol: str, 
                              interval: str, limit: int) -> list:
    """Получение klines с кэшированием"""
    cache_key = get_cache_key(symbol, interval, limit)
    current_time = time.time()
    
    # Проверяем кэш
    if cache_key in _KLINES_CACHE:
        cached_data, timestamp = _KLINES_CACHE[cache_key]
        if current_time - timestamp < _CACHE_TTL:
            return cached_data
    
    # Запрашиваем данные
    klines = await fetch_klines(session, symbol, interval, limit)
    
    # Сохраняем в кэш
    _KLINES_CACHE[cache_key] = (klines, current_time)
    
    # Очищаем старые записи из кэша
    if len(_KLINES_CACHE) > 1000:
        old_keys = [k for k, (_, ts) in _KLINES_CACHE.items() 
                   if current_time - ts > _CACHE_TTL * 2]
        for k in old_keys:
            del _KLINES_CACHE[k]
    
    return klines


# ============================================================================
# WHALE ACTIVITY DETECTION
# ============================================================================

def detect_whale_walls(orderbook: dict, threshold_multiplier: float = 10.0) -> dict:
    """
    Детекция крупных стен в orderbook (китовая активность)
    
    Args:
        orderbook: Стакан заявок
        threshold_multiplier: Во сколько раз ордер должен быть больше среднего
    
    Returns:
        dict с информацией о китовых стенах
    """
    if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
        return {'whale_bid': None, 'whale_ask': None, 'bias': 'neutral'}
    
    bids = orderbook['bids'][:20]  # Топ 20 bid ордеров
    asks = orderbook['asks'][:20]  # Топ 20 ask ордеров
    
    if not bids or not asks:
        return {'whale_bid': None, 'whale_ask': None, 'bias': 'neutral'}
    
    # Средний размер ордера
    avg_bid_size = sum(float(b[1]) for b in bids) / len(bids)
    avg_ask_size = sum(float(a[1]) for a in asks) / len(asks)
    
    # Ищем крупные стены
    whale_bids = [(float(b[0]), float(b[1])) for b in bids 
                  if float(b[1]) > avg_bid_size * threshold_multiplier]
    whale_asks = [(float(a[0]), float(a[1])) for a in asks 
                  if float(a[1]) > avg_ask_size * threshold_multiplier]
    
    # Определяем bias
    total_whale_bid_volume = sum(b[1] for b in whale_bids)
    total_whale_ask_volume = sum(a[1] for a in whale_asks)
    
    bias = 'neutral'
    if total_whale_bid_volume > total_whale_ask_volume * 1.5:
        bias = 'bullish'  # Крупная поддержка
    elif total_whale_ask_volume > total_whale_bid_volume * 1.5:
        bias = 'bearish'  # Крупное сопротивление
    
    return {
        'whale_bid': whale_bids[0] if whale_bids else None,
        'whale_ask': whale_asks[0] if whale_asks else None,
        'bias': bias,
        'whale_bid_count': len(whale_bids),
        'whale_ask_count': len(whale_asks)
    }


# ============================================================================
# CORRELATION FILTERING
# ============================================================================

async def check_btc_correlation(symbol: str, btc_trend: int, signal_type: str) -> bool:
    """
    Проверка корреляции с BTC для фильтрации контртрендовых сигналов
    
    Args:
        symbol: Торговая пара
        btc_trend: Тренд BTC (-10 до 10)
        signal_type: Тип сигнала
    
    Returns:
        True если сигнал валидный, False если нужно отфильтровать
    """
    # Если это сам BTC - пропускаем
    if symbol == "BTCUSDT":
        return True
    
    # Если BTC в сильном падении и сигнал на PUMP - фильтруем
    if btc_trend < -5 and ("PUMP" in signal_type or "Dump → Pump" in signal_type):
        return False
    
    # Если BTC в сильном росте и сигнал на DUMP - фильтруем
    if btc_trend > 5 and ("DUMP" in signal_type or "Pump → Dump" in signal_type):
        return False
    
    return True


# ============================================================================
# УЛУЧШЕННАЯ СИСТЕМА ЛОГИРОВАНИЯ
# ============================================================================

class ErrorCategory:
    """Категории ошибок для разной логики обработки"""
    API_ERROR = "API"
    DATA_ERROR = "DATA"
    ANALYSIS_ERROR = "ANALYSIS"
    NETWORK_ERROR = "NETWORK"
    UNKNOWN = "UNKNOWN"


def categorize_error(e: Exception) -> str:
    """Определение категории ошибки"""
    error_str = str(e).lower()
    
    if 'timeout' in error_str or 'connection' in error_str:
        return ErrorCategory.NETWORK_ERROR
    elif 'api' in error_str or 'rate limit' in error_str:
        return ErrorCategory.API_ERROR
    elif 'data' in error_str or 'parse' in error_str or 'json' in error_str:
        return ErrorCategory.DATA_ERROR
    elif 'calculation' in error_str or 'divide' in error_str:
        return ErrorCategory.ANALYSIS_ERROR
    else:
        return ErrorCategory.UNKNOWN


def log_error_categorized(e: Exception, context: str = ""):
    """Улучшенное логирование ошибок с категориями"""
    category = categorize_error(e)
    
    with open("errors.log", "a", encoding="utf-8") as f:
        f.write(
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"[{category}] | {context} | {repr(e)}\n"
        )
        f.write(traceback.format_exc() + "\n")
    
    # Отдельный лог для критических ошибок
    if category in [ErrorCategory.API_ERROR, ErrorCategory.NETWORK_ERROR]:
        with open("critical_errors.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {category} | {repr(e)}\n")


# Оригинальная функция для совместимости
def log_error(e: Exception):
    log_error_categorized(e, "")


# ============================================================================
# ОРИГИНАЛЬНЫЕ ФУНКЦИИ (без изменений для совместимости)
# ============================================================================

def symbol_on_cooldown(symbol: str) -> bool:
    ts = _last_signal_ts.get(symbol)
    if ts is None:
        return False
    return (time.time() - ts) < SYMBOL_COOLDOWN


def mark_symbol_signal(symbol: str):
    _last_signal_ts[symbol] = time.time()


def log_signal(s: dict):
    with open("signals.log", "a", encoding="utf-8") as f:
        f.write(
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"{s['type']} | {s['symbol']} | price={s['price']:.4f} | "
            f"rating={s['rating']} | trend={s['trend_score']} | risk={s['risk_score']}\n"
        )


def apply_reversal_filters(signal_type, closes, highs, lows, volumes, delta_status):
    if len(closes) < 5:
        return 0

    c0, c1, c2 = closes[0], closes[1], closes[2]
    h0, h1 = highs[0], highs[1]
    l0, l1 = lows[0], lows[1]
    v0, v1 = volumes[0], volumes[1]

    adj = 0

    is_bullish = any(x in signal_type for x in ["Dump → Pump", "PUMP"])
    is_bearish = any(x in signal_type for x in ["Pump → Dump", "DUMP"])

    if is_bullish:
        if c0 > c1 and (c0 - c1) / max(c1, 1e-7) * 100 > 0.2:
            adj += 7
        if c0 < c1 and (c1 - c0) / max(c1, 1e-7) * 100 > 0.2:
            adj -= 5

    if is_bearish:
        if c0 < c1 and (c1 - c0) / max(c1, 1e-7) * 100 > 0.2:
            adj += 7
        if c0 > c1 and (c0 - c1) / max(c1, 1e-7) * 100 > 0.2:
            adj -= 5

    if is_bearish and h0 > h1:
        diff = (h0 - h1) / max(h1, 1e-7) * 100
        if 0.1 < diff < 0.4 and v0 < v1:
            adj += 5

    if is_bullish and l0 < l1:
        diff = (l1 - l0) / max(l1, 1e-7) * 100
        if 0.1 < diff < 0.4 and v0 < v1:
            adj += 5

    if is_bullish:
        if delta_status == "bullish":
            adj += 3
        elif delta_status == "bearish":
            adj -= 3

    if is_bearish:
        if delta_status == "bearish":
            adj += 3
        elif delta_status == "bullish":
            adj -= 3

    if is_bullish:
        if c2 > c1 and c0 > c1:
            diff = abs(c1 - c2) / max(c2, 1e-7) * 100
            if diff < 0.6:
                adj += 5

    if is_bearish:
        if c2 < c1 and c0 < c1:
            diff = abs(c1 - c2) / max(c2, 1e-7) * 100
            if diff < 0.6:
                adj += 5

    return adj


def generate_candle_chart(klines, symbol: str, timeframe_label: str = "15m"):
    if not klines:
        return None

    df = pd.DataFrame({
        "Open":   [float(c[1]) for c in klines],
        "High":   [float(c[2]) for c in klines],
        "Low":    [float(c[3]) for c in klines],
        "Close":  [float(c[4]) for c in klines],
        "Volume": [float(c[5]) for c in klines],
    })

    df.index = pd.to_datetime([int(c[0]) for c in klines], unit="ms")
    df = df.iloc[::-1]

    mc = mpf.make_marketcolors(up='green', down='red', inherit=True)
    style = mpf.make_mpf_style(marketcolors=mc)

    buf = BytesIO()
    mpf.plot(df, type="candle", volume=True, style=style,
             title=f"{symbol} — {timeframe_label}", savefig=buf)
    buf.seek(0)
    return buf


def compute_htf_trend_from_klines(klines):
    if not klines or len(klines) < 20:
        return 0
    closes = [float(c[4]) for c in klines][::-1]
    c0 = closes[0]
    cN = closes[min(len(closes) - 1, 30)]
    if cN <= 0:
        return 0
    change_pct = (c0 - cN) / cN * 100
    if change_pct > 2:
        return 5
    if change_pct > 0.7:
        return 3
    if change_pct < -2:
        return -5
    if change_pct < -0.7:
        return -3
    return 0


def ema(values, period: int):
    if not values or period <= 1 or len(values) < period:
        return values[:]
    k = 2 / (period + 1)
    ema_vals = []
    prev = sum(values[:period]) / period
    ema_vals.extend(values[:period - 1])
    ema_vals.append(prev)
    for v in values[period:]:
        prev = v * k + prev * (1 - k)
        ema_vals.append(prev)
    return ema_vals


def compute_atr_from_klines(klines, period: int = 14) -> float:
    if not klines or len(klines) < period + 1:
        return 0.0

    highs = [float(c[2]) for c in klines][::-1]
    lows = [float(c[3]) for c in klines][::-1]
    closes = [float(c[4]) for c in klines][::-1]

    trs = []
    for i in range(1, len(closes)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        trs.append(tr)

    if len(trs) < period:
        return sum(trs) / max(len(trs), 1)

    return sum(trs[-period:]) / period


# ============================================================================
# ГЛАВНАЯ ФУНКЦИЯ АНАЛИЗА (с улучшениями)
# ============================================================================

async def analyze_symbol_async(
    session: aiohttp.ClientSession,
    symbol: str,
    min_score: int,
    ticker_info: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Улучшенная версия analyze_symbol_async с:
    - Кэшированием klines
    - Volume profile анализом
    - Whale detection
    - Адаптивным min_score
    - Position sizing
    - BTC correlation filtering
    """
    
    try:
        # Проверка cooldown
        if symbol_on_cooldown(symbol):
            return None
        
        # Используем кэшированные klines где возможно
        klines_1m = await fetch_klines_cached(session, symbol, interval="1", limit=120)
        klines_15m = await fetch_klines_cached(session, symbol, interval="15", limit=96)
        klines_1h = await fetch_klines_cached(session, symbol, interval="60", limit=96)
        klines_4h = await fetch_klines_cached(session, symbol, interval="240", limit=96)
        
        if not klines_1m:
            return None
        
        # Получаем BTC контекст
        btc_ctx = await _get_or_update_btc_context(session)
        btc_factor = btc_ctx.get("factor", 1.0)
        btc_regime = btc_ctx.get("regime", "neutral")
        
        # Адаптивный min_score
        adaptive_min_score = get_adaptive_min_score(btc_regime, btc_factor, min_score)
        
        # Базовые данные
        last_price = float(klines_1m[0][4])
        closes_1m = [float(c[4]) for c in klines_1m][::-1]
        highs_1m = [float(c[2]) for c in klines_1m][::-1]
        lows_1m = [float(c[3]) for c in klines_1m][::-1]
        volumes_1m = [float(c[5]) for c in klines_1m][::-1]
        
        # Тренды на разных таймфреймах
        trend_15m = compute_htf_trend_from_klines(klines_15m)
        trend_1h = compute_htf_trend_from_klines(klines_1h)
        trend_4h = compute_htf_trend_from_klines(klines_4h)
        
        # Основные показатели
        trend_score = compute_trend_score(closes_1m, volumes_1m)
        risk_score = compute_risk_score(closes_1m, volumes_1m)
        
        # Дополнительные данные
        oi_data = await fetch_open_interest(session, symbol)
        funding_rate = await fetch_funding_rate(session, symbol)
        liquidations = await fetch_liquidations(session, symbol)
        trades = await fetch_recent_trades(session, symbol, limit=500)
        orderbook = await fetch_orderbook(session, symbol, limit=20)
        
        # Анализ ликвидаций, flow, delta
        liq_status = interpret_liquidations(liquidations)
        flow_status = analyze_flow_from_trades(trades)
        delta_status = analyze_delta_from_trades(trades)
        
        # OI анализ
        oi_now = oi_data[-1]["openInterest"] if oi_data else 0
        oi_prev = oi_data[-2]["openInterest"] if len(oi_data) > 1 else oi_now
        oi_status = "rising" if oi_now > oi_prev else "falling" if oi_now < oi_prev else "flat"
        
        # Volume Profile Analysis (новое!)
        vol_profile = compute_volume_profile(klines_15m)
        
        # Whale Activity Detection (новое!)
        whale_info = detect_whale_walls(orderbook)
        
        # Liquidity map
        liq_map = build_liquidity_map(symbol, orderbook, last_price)
        liq_bias = liq_map.get("bias", "neutral")
        liq_strongest = liq_map.get("strongest_zone")
        liq_vac_up = liq_map.get("vacuum_up", False)
        liq_vac_down = liq_map.get("vacuum_down", False)
        
        # HTF структура
        structure_1h = compute_htf_structure(klines_1h)
        structure_4h = compute_htf_structure(klines_4h)
        swings_1h = detect_swings(klines_1h)
        swings_4h = detect_swings(klines_4h)
        
        event_1h = structure_1h.get("last_event", {})
        event_4h = structure_4h.get("last_event", {})
        
        # Microstructure
        price_buckets = build_price_buckets(klines_1m, num_buckets=10)
        micro = analyze_microstructure(price_buckets, closes_1m)
        
        # Footprint zones
        footprint_zones = compute_footprint_zones(klines_1m, trades)
        
        # Impulse score
        impulse_score = 0
        if len(closes_1m) >= 3:
            c0, c1, c2 = closes_1m[0], closes_1m[1], closes_1m[2]
            if c0 > c1 > c2:
                impulse_score = 5
            elif c0 < c1 < c2:
                impulse_score = -5
        
        # Детекция паттернов
        candidates = []
        
        settings = load_settings()
        strictness_level = settings.get("strictness_level", "medium")
        reversal_requires_state = settings.get("reversal_requires_state", False)
        reversal_min_delay_bars = settings.get("reversal_min_delay_bars", 3)
        reversal_min_score_bonus = settings.get("reversal_min_score_bonus", 0)
        
        reversal_state = get_symbol_state(symbol)
        
        # Big Pump detection
        pump = detect_big_pump(klines_1m)
        if pump.get("detected") and pump.get("rating", 0) >= adaptive_min_score:
            adj = adjust_rating_with_context(
                pump["rating"],
                "BIG PUMP",
                closes_1m,
                oi_now,
                oi_prev,
                funding_rate,
                liq_status,
                flow_status,
                delta_status,
                trend_score,
                risk_score,
            )
            
            # BTC correlation check (новое!)
            if await check_btc_correlation(symbol, trend_1h, "BIG PUMP"):
                candidates.append({
                    "symbol": symbol,
                    "type": "BIG PUMP",
                    "emoji": "🚀",
                    "price": last_price,
                    "rating": adj,
                    "oi": oi_status,
                    "funding": funding_rate,
                    "liq": liq_status,
                    "flow": flow_status,
                    "delta": delta_status,
                    "trend_score": trend_score,
                    "risk_score": risk_score,
                    "trend_15m": trend_15m,
                    "trend_1h": trend_1h,
                    "trend_4h": trend_4h,
                    "meta_closes": closes_1m,
                    "meta_highs": highs_1m,
                    "meta_lows": lows_1m,
                    "liq_map_bias": liq_bias,
                    "liq_map_strongest": liq_strongest,
                    "liq_map_vac_up": liq_vac_up,
                    "liq_map_vac_down": liq_vac_down,
                    "vol_profile": vol_profile,  # новое!
                    "whale_activity": whale_info,  # новое!
                })
        
        # Big Dump detection
        dump = detect_big_dump(klines_1m)
        if dump.get("detected") and dump.get("rating", 0) >= adaptive_min_score:
            adj = adjust_rating_with_context(
                dump["rating"],
                "BIG DUMP",
                closes_1m,
                oi_now,
                oi_prev,
                funding_rate,
                liq_status,
                flow_status,
                delta_status,
                trend_score,
                risk_score,
            )
            
            # BTC correlation check (новое!)
            if await check_btc_correlation(symbol, trend_1h, "BIG DUMP"):
                candidates.append({
                    "symbol": symbol,
                    "type": "BIG DUMP",
                    "emoji": "💥",
                    "price": last_price,
                    "rating": adj,
                    "oi": oi_status,
                    "funding": funding_rate,
                    "liq": liq_status,
                    "flow": flow_status,
                    "delta": delta_status,
                    "trend_score": trend_score,
                    "risk_score": risk_score,
                    "trend_15m": trend_15m,
                    "trend_1h": trend_1h,
                    "trend_4h": trend_4h,
                    "meta_closes": closes_1m,
                    "meta_highs": highs_1m,
                    "meta_lows": lows_1m,
                    "liq_map_bias": liq_bias,
                    "liq_map_strongest": liq_strongest,
                    "liq_map_vac_up": liq_vac_up,
                    "liq_map_vac_down": liq_vac_down,
                    "vol_profile": vol_profile,
                    "whale_activity": whale_info,
                })
        
        # Reversal detection
        rev = detect_pump_reversal(klines_1m, micro, footprint_zones, swings_1h, swings_4h)
        if rev.get("reversal") and rev.get("rating", 0) >= adaptive_min_score:
            direction = "Dump → Pump" if rev["reversal"] == "bullish" else "Pump → Dump"
            adj = adjust_rating_with_context(
                rev["rating"],
                f"REVERSAL {direction}",
                closes_1m,
                oi_now,
                oi_prev,
                funding_rate,
                liq_status,
                flow_status,
                delta_status,
                trend_score,
                risk_score,
            )
            adj += apply_reversal_filters(direction, closes_1m, highs_1m, lows_1m, volumes_1m, delta_status)
            
            # BTC correlation check (новое!)
            if await check_btc_correlation(symbol, trend_1h, f"REVERSAL {direction}"):
                # Проверки на фильтры (упрощены для примера)
                candidates.append({
                    "symbol": symbol,
                    "type": f"REVERSAL {direction}",
                    "emoji": "🔵",
                    "price": last_price,
                    "rating": adj,
                    "oi": oi_status,
                    "funding": funding_rate,
                    "liq": liq_status,
                    "flow": flow_status,
                    "delta": delta_status,
                    "trend_score": trend_score,
                    "risk_score": risk_score,
                    "trend_15m": trend_15m,
                    "trend_1h": trend_1h,
                    "trend_4h": trend_4h,
                    "meta_closes": closes_1m,
                    "meta_highs": highs_1m,
                    "meta_lows": lows_1m,
                    "liq_map_bias": liq_bias,
                    "liq_map_strongest": liq_strongest,
                    "liq_map_vac_up": liq_vac_up,
                    "liq_map_vac_down": liq_vac_down,
                    "vol_profile": vol_profile,
                    "whale_activity": whale_info,
                })
        
        if not candidates:
            return None
        
        # Symbol memory
        symbol_mem = get_symbol_memory(symbol)
        symbol_profile = symbol_mem.get("profile", {}) if symbol_mem else {}
        symbol_regime = symbol_profile.get("regime", "neutral")
        
        # Обработка кандидатов с smart filters
        for c in candidates:
            base = c["rating"]
            t = c["type"]
            
            direction_side = "bullish" if any(x in t for x in ["PUMP", "Dump → Pump"]) else "bearish"
            
            base += impulse_score
            base = base * btc_factor
            
            # BTC regime adjustments
            if btc_regime == "trending" and ("PUMP" in t or "DUMP" in t):
                base *= 1.05
            if btc_regime == "ranging" and "REVERSAL" in t:
                base *= 1.07
            if btc_regime == "high_vol":
                base *= 0.9
            
            # Symbol memory bias
            mem_bias = 0.0
            if symbol_regime == "pumpy" and "PUMP" in t:
                mem_bias += 10.0
            if symbol_regime == "dumpy" and "DUMP" in t:
                mem_bias += 10.0
            if symbol_regime == "mean_reverting" and "REVERSAL" in t:
                mem_bias += 8.0
            if symbol_regime == "chaotic":
                mem_bias -= 12.0
            
            base += mem_bias
            
            # Smart filters v3
            extra_filters_ok = {
                "min_score_ok": base >= adaptive_min_score,
                "oi_not_falling": oi_status != "falling",
                "liq_not_contra_bull": not (direction_side == "bullish" and liq_bias == "bearish"),
                "liq_not_contra_bear": not (direction_side == "bearish" and liq_bias == "bullish"),
            }
            
            sf3 = apply_smartfilters_v3(
                symbol=symbol,
                base_rating=int(base),
                direction_side=direction_side,
                closes_1m=closes_1m,
                klines_1m=klines_1m,
                trend_score=trend_score,
                trend_15m=trend_15m,
                trend_1h=trend_1h,
                trend_4h=trend_4h,
                liquidity_bias=liq_bias,
                noise_level=None,
                btc_ctx=btc_ctx,
                extra_filters_ok=extra_filters_ok,
                global_risk_proxy=None,
            )
            
            c["rating"] = sf3["final_rating"]
            c["confidence"] = sf3["confidence"]
            c["symbol_regime"] = sf3["symbol_regime"]
            c["market_ctx"] = sf3["market_ctx"]
            c["vol_cluster"] = sf3["vol_cluster"]
            c["memory_ctx"] = sf3["memory_ctx"]
            c["sf3_weights"] = sf3["weights"]
            c["symbol_memory_profile"] = symbol_profile
            
            # Финальная коррекция рейтинга
            c["rating"] = max(0, min(int(c["rating"]), 100))
            
            # Добавляем Stop Loss / Take Profit и position sizing (новое!)
            atr_1m = compute_atr_from_klines(klines_1m)
            c = add_sl_tp_to_signal(c, last_price, atr_1m)
        
        # Выбираем лучший сигнал
        candidates.sort(key=lambda x: x["rating"], reverse=True)
        best = candidates[0]
        
        # Обновляем symbol memory
        atr_1m = compute_atr_from_klines(klines_1m)
        snapshot = {
            "atr_1m": atr_1m,
            "trend_score": trend_score,
            "is_pump": "PUMP" in best["type"],
            "is_dump": "DUMP" in best["type"],
            "btc_factor": btc_factor,
        }
        updated_mem = update_symbol_memory(symbol, snapshot)
        best["symbol_memory"] = updated_mem
        
        # Логируем и маркируем
        log_signal(best)
        mark_symbol_signal(symbol)
        
        # Добавляем в performance tracker (новое!)
        signal_id = performance_tracker.add_signal(best)
        best["signal_id"] = signal_id
        
        return best
        
    except Exception as e:
        log_error_categorized(e, f"analyze_symbol_async({symbol})")
        return None


async def _get_or_update_btc_context(session: aiohttp.ClientSession) -> dict:
    """Получение или обновление контекста BTC"""
    current_time = time.time()
    
    # Кэш на 2 минуты
    if current_time - _BTC_CTX_CACHE["ts"] < 120:
        return {
            "factor": _BTC_CTX_CACHE["factor"],
            "regime": _BTC_CTX_CACHE["regime"]
        }
    
    try:
        # Получаем BTC данные
        btc_klines = await fetch_klines_cached(session, "BTCUSDT", interval="15", limit=50)
        if not btc_klines:
            return {"factor": 1.0, "regime": "neutral"}
        
        btc_closes = [float(k[4]) for k in btc_klines][::-1]
        btc_volumes = [float(k[5]) for k in btc_klines][::-1]
        
        # Анализируем BTC
        btc_trend = compute_trend_score(btc_closes, btc_volumes)
        btc_atr = compute_atr_from_klines(btc_klines)
        btc_price = btc_closes[0]
        
        # Определяем режим
        regime = "neutral"
        factor = 1.0
        
        volatility = (btc_atr / btc_price) * 100 if btc_price > 0 else 0
        
        if volatility > 0.5:
            regime = "high_vol"
            factor = 0.9
        elif abs(btc_trend) > 5:
            regime = "trending"
            factor = 1.1
        elif abs(btc_trend) < 2:
            regime = "ranging"
            factor = 1.05
        
        # Обновляем кэш
        _BTC_CTX_CACHE["ts"] = current_time
        _BTC_CTX_CACHE["factor"] = factor
        _BTC_CTX_CACHE["regime"] = regime
        
        return {"factor": factor, "regime": regime}
        
    except Exception as e:
        log_error(e)
        return {"factor": 1.0, "regime": "neutral"}


# ============================================================================
# УЛУЧШЕННЫЙ SCANNER LOOP
# ============================================================================

async def scanner_loop(send_text, send_photo, min_score: int, engine=None):
    """
    Улучшенный основной цикл сканера с:
    - Ограничением параллельных запросов
    - Performance tracking
    - Адаптивным min_score
    - Алертами на деградацию модели
    """
    
    # Семафор для ограничения параллельных запросов
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    async def analyze_with_limit(session, symbol, min_score, tinfo):
        async with semaphore:
            return await analyze_symbol_async(session, symbol, min_score, tinfo)
    
    async with aiohttp.ClientSession() as session:
        iteration = 0
        
        while True:
            try:
                iteration += 1
                
                # Получаем тикеры
                tickers = await fetch_tickers(session)
                
                symbols = [
                    (t["symbol"], t)
                    for t in tickers
                    if t.get("symbol", "").endswith("USDT")
                ]
                
                # Параллельный анализ с ограничением
                tasks = [
                    analyze_with_limit(session, s, min_score, tinfo)
                    for s, tinfo in symbols
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                signals = [r for r in results if isinstance(r, dict)]
                
                if signals:
                    signals.sort(key=lambda x: x["rating"], reverse=True)
                    
                    # Отправляем топ 10 сигналов
                    for s in signals[:10]:
                        symbol_regime = s.get("symbol_regime", {}) or {}
                        market_ctx = s.get("market_ctx", {}) or {}
                        vol_cluster = s.get("vol_cluster", {}) or {}
                        mem_profile = (s.get("symbol_memory") or {}).get("profile", {}) or {}
                        position_info = s.get("position_sizing", {})
                        vol_profile = s.get("vol_profile", {})
                        whale_info = s.get("whale_activity", {})
                        
                        # Форматированный текст с новыми данными
                        text = (
                            f"{s['emoji']} {s['type']} — {s['symbol']}\n"
                            f"Цена: {s['price']:.4f} USDT\n"
                            f"Сила сигнала: {s['rating']}/100\n"
                            f"Уверенность: {s.get('confidence', 0):.2f}\n"
                            f"Trend Score: {s['trend_score']}\n"
                            f"Risk Score: {s['risk_score']}\n"
                            f"HTF 15m: {s.get('trend_15m', 0)} | 1h: {s.get('trend_1h', 0)} | 4h: {s.get('trend_4h', 0)}\n"
                            f"Symbol Regime: {symbol_regime.get('regime')} (strength={symbol_regime.get('strength')})\n"
                            f"Market Regime: {market_ctx.get('market_regime')} | Risk: {market_ctx.get('risk')}\n"
                            f"Vol Cluster: {vol_cluster.get('cluster')} | VolScore: {vol_cluster.get('volatility_score')}\n"
                            f"Symbol Memory Regime: {mem_profile.get('regime')} | PumpProb: {mem_profile.get('pump_probability'):.2f} | DumpProb: {mem_profile.get('dump_probability'):.2f}\n"
                            f"OI: {s['oi']}\n"
                            f"{format_funding_text(s['funding'])}\n"
                            f"{format_liq_text(s['liq'])}\n"
                            f"{format_flow_text(s['flow'])}\n"
                            f"{format_delta_text(s['delta'])}\n"
                            f"Liquidity Bias: {s.get('liq_map_bias')}\n"
                            f"Strongest Zone: {s.get('liq_map_strongest')}\n"
                            f"Vacuum Up: {s.get('liq_map_vac_up')} | Down: {s.get('liq_map_vac_down')}\n"
                            f"\n📊 VOLUME PROFILE:\n"
                            f"POC: {vol_profile.get('poc', 'N/A')} | VPOC: {vol_profile.get('vpoc', 'N/A')}\n"
                            f"\n🐋 WHALE ACTIVITY:\n"
                            f"Bias: {whale_info.get('bias', 'neutral')} | Walls: Bid={whale_info.get('whale_bid_count', 0)} Ask={whale_info.get('whale_ask_count', 0)}\n"
                            f"\n💰 POSITION SIZING:\n"
                            f"Size: {position_info.get('position_size_usdt', 0):.2f} USDT\n"
                            f"Stop Loss: {s.get('stop_loss', 0):.4f} ({position_info.get('sl_distance_percent', 0):.2f}%)\n"
                            f"Take Profit 1: {s.get('take_profit_1', 0):.4f} ({position_info.get('tp_conservative_percent', 0):.2f}%)\n"
                            f"Take Profit 2: {s.get('take_profit_2', 0):.4f} ({position_info.get('tp_aggressive_percent', 0):.2f}%)\n"
                            f"Risk: {position_info.get('risk_amount_usdt', 0):.2f} USDT | Quality: {position_info.get('quality_score', 0):.1f}\n"
                        )
                        
                        await send_text(text)
                        
                        # Генерируем и отправляем график
                        klines_15m = await fetch_klines(session, s["symbol"], interval="15", limit=96)
                        chart = generate_candle_chart(klines_15m, s["symbol"], timeframe_label="15m")
                        
                        if chart:
                            photo = BufferedInputFile(chart.getvalue(), filename=f"{s['symbol']}.png")
                            await send_photo(photo)
                        
                        # Вызываем engine если есть
                        if engine is not None:
                            await engine.on_signal(s)
                
                # Каждые 10 итераций - проверяем outcomes и отправляем статистику
                if iteration % 10 == 0:
                    # Проверяем outcomes старых сигналов
                    for signal_id in list(performance_tracker.signals.keys()):
                        await performance_tracker.check_signal_outcome(signal_id, session, check_minutes=15)
                    
                    # Отправляем статистику
                    stats_text = performance_tracker.get_stats_text()
                    await send_text(stats_text)
                    
                    # Проверяем на деградацию
                    if performance_tracker.should_alert_degradation():
                        alert_text = (
                            "⚠️ ВНИМАНИЕ! Модель деградирует!\n"
                            f"Win Rate упал ниже 45%\n"
                            f"{stats_text}"
                        )
                        await send_text(alert_text)
                
                await asyncio.sleep(30)
                
            except Exception as e:
                log_error_categorized(e, "scanner_loop")
                try:
                    await send_text(f"⚠️ Ошибка в сканере, перезапускаю цикл...\n{repr(e)}")
                except:
                    pass
                await asyncio.sleep(5)
                continue
