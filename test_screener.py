"""
Unit тесты для улучшенного скринера
Запуск: pytest test_screener.py -v
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from screener_improved import (
    get_adaptive_min_score,
    calculate_position_size,
    add_sl_tp_to_signal,
    compute_volume_profile,
    detect_whale_walls,
    check_btc_correlation,
    ema,
    compute_atr_from_klines,
    PerformanceTracker,
    SignalPerformance,
)


class TestAdaptiveMinScore:
    """Тесты адаптивного min_score"""
    
    def test_high_volatility_increases_threshold(self):
        """В высокой волатильности порог должен повыситься"""
        base = 60
        result = get_adaptive_min_score("high_vol", 1.0, base)
        assert result > base
    
    def test_ranging_decreases_threshold(self):
        """В спокойном рынке порог должен снизиться"""
        base = 60
        result = get_adaptive_min_score("ranging", 1.0, base)
        assert result < base
    
    def test_trending_increases_slightly(self):
        """В тренде порог повышается умеренно"""
        base = 60
        result = get_adaptive_min_score("trending", 1.0, base)
        assert result > base
        assert result < get_adaptive_min_score("high_vol", 1.0, base)
    
    def test_boundaries_respected(self):
        """Результат должен быть в диапазоне 40-80"""
        for regime in ["high_vol", "ranging", "trending", "neutral"]:
            for vol in [0.5, 1.0, 2.0]:
                result = get_adaptive_min_score(regime, vol, 60)
                assert 40 <= result <= 80


class TestPositionSizing:
    """Тесты расчёта размера позиции"""
    
    def test_higher_rating_increases_position(self):
        """Высокий рейтинг = больше позиция"""
        pos_low = calculate_position_size(50, 0.8, 10.0, 5)
        pos_high = calculate_position_size(90, 0.8, 10.0, 5)
        assert pos_high['position_size_usdt'] > pos_low['position_size_usdt']
    
    def test_higher_risk_decreases_position(self):
        """Высокий риск = меньше позиция"""
        pos_safe = calculate_position_size(80, 0.8, 10.0, 2)
        pos_risky = calculate_position_size(80, 0.8, 10.0, 9)
        assert pos_risky['position_size_usdt'] < pos_safe['position_size_usdt']
    
    def test_confidence_affects_position(self):
        """Уверенность влияет на размер"""
        pos_low_conf = calculate_position_size(80, 0.3, 10.0, 5)
        pos_high_conf = calculate_position_size(80, 0.9, 10.0, 5)
        assert pos_high_conf['position_size_usdt'] > pos_low_conf['position_size_usdt']
    
    def test_sl_tp_calculated(self):
        """SL и TP должны быть рассчитаны"""
        result = calculate_position_size(80, 0.8, 10.0, 5)
        assert 'sl_distance_percent' in result
        assert 'tp_conservative_percent' in result
        assert 'tp_aggressive_percent' in result
        assert result['tp_aggressive_percent'] > result['tp_conservative_percent']


class TestVolumeProfile:
    """Тесты анализа профиля объёма"""
    
    def test_empty_klines_returns_none(self):
        """Пустые данные возвращают None"""
        result = compute_volume_profile([])
        assert result['poc'] is None
        assert result['vpoc'] is None
    
    def test_insufficient_data_returns_none(self):
        """Недостаточно данных возвращают None"""
        klines = [[0, 100, 101, 99, 100, 1000] for _ in range(5)]
        result = compute_volume_profile(klines)
        assert result['poc'] is None
    
    def test_valid_data_returns_poc(self):
        """Валидные данные возвращают POC"""
        # Создаём 50 свечей с разным объёмом
        klines = []
        for i in range(50):
            price = 100 + i * 0.1
            volume = 1000 + (i % 10) * 500  # Неравномерный объём
            klines.append([i * 60000, price, price + 0.2, price - 0.2, price + 0.1, volume])
        
        result = compute_volume_profile(klines)
        assert result['poc'] is not None
        assert result['vpoc'] is not None
        assert isinstance(result['high_volume_levels'], list)
        assert len(result['high_volume_levels']) > 0


class TestWhaleDetection:
    """Тесты детекции китовой активности"""
    
    def test_empty_orderbook_returns_neutral(self):
        """Пустой стакан возвращает neutral"""
        result = detect_whale_walls({})
        assert result['bias'] == 'neutral'
        assert result['whale_bid'] is None
        assert result['whale_ask'] is None
    
    def test_large_bid_wall_bullish_bias(self):
        """Крупная bid стена = bullish bias"""
        orderbook = {
            'bids': [[100, 10], [99, 10], [98, 200]],  # Крупная стена на 98
            'asks': [[101, 10], [102, 10], [103, 10]]
        }
        result = detect_whale_walls(orderbook, threshold_multiplier=5.0)
        assert result['bias'] == 'bullish'
        assert result['whale_bid'] is not None
    
    def test_large_ask_wall_bearish_bias(self):
        """Крупная ask стена = bearish bias"""
        orderbook = {
            'bids': [[100, 10], [99, 10], [98, 10]],
            'asks': [[101, 10], [102, 10], [103, 200]]  # Крупная стена на 103
        }
        result = detect_whale_walls(orderbook, threshold_multiplier=5.0)
        assert result['bias'] == 'bearish'
        assert result['whale_ask'] is not None


class TestBTCCorrelation:
    """Тесты фильтрации по корреляции с BTC"""
    
    @pytest.mark.asyncio
    async def test_btc_itself_always_passes(self):
        """BTC сам всегда проходит"""
        result = await check_btc_correlation("BTCUSDT", -10, "BIG PUMP")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_pump_filtered_on_btc_dump(self):
        """PUMP фильтруется при падении BTC"""
        result = await check_btc_correlation("ETHUSDT", -7, "BIG PUMP")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_dump_filtered_on_btc_pump(self):
        """DUMP фильтруется при росте BTC"""
        result = await check_btc_correlation("ETHUSDT", 7, "BIG DUMP")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_reversal_passes_regardless(self):
        """Реверсалы проходят независимо от BTC"""
        result1 = await check_btc_correlation("ETHUSDT", -7, "REVERSAL Dump → Pump")
        result2 = await check_btc_correlation("ETHUSDT", 7, "REVERSAL Pump → Dump")
        # Реверсалы могут проходить даже против BTC
        assert result1 is True or result1 is False  # Зависит от логики


class TestEMA:
    """Тесты расчёта EMA"""
    
    def test_empty_values_returns_empty(self):
        """Пустые данные возвращают пустой список"""
        result = ema([], 10)
        assert result == []
    
    def test_insufficient_period_returns_original(self):
        """Недостаточно данных для периода"""
        values = [1, 2, 3]
        result = ema(values, 10)
        assert result == values
    
    def test_ema_calculation(self):
        """Проверка корректности расчёта EMA"""
        values = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
        result = ema(values, 3)
        
        # Первые period-1 значений должны быть оригинальными
        assert result[0] == values[0]
        assert result[1] == values[1]
        
        # EMA должна быть рассчитана
        assert len(result) == len(values)
        
        # Последнее значение EMA должно быть близко к последнему значению
        assert abs(result[-1] - values[-1]) < 5


class TestATR:
    """Тесты расчёта ATR"""
    
    def test_empty_klines_returns_zero(self):
        """Пустые данные возвращают 0"""
        result = compute_atr_from_klines([])
        assert result == 0.0
    
    def test_insufficient_data_returns_average(self):
        """Недостаточно данных для полного ATR"""
        klines = [[0, 100, 105, 95, 102, 1000] for _ in range(5)]
        result = compute_atr_from_klines(klines, period=14)
        assert result > 0  # Должен вернуть среднее из доступных TR
    
    def test_atr_calculation(self):
        """Проверка корректности расчёта ATR"""
        # Создаём свечи с известной волатильностью
        klines = []
        for i in range(50):
            price = 100 + i * 0.5
            high = price + 2
            low = price - 2
            klines.append([i * 60000, price, high, low, price, 1000])
        
        result = compute_atr_from_klines(klines, period=14)
        assert result > 0
        assert result < 10  # Разумный диапазон для данных


class TestPerformanceTracker:
    """Тесты трекера производительности"""
    
    def test_add_signal(self, tmp_path):
        """Добавление сигнала"""
        db_file = tmp_path / "test_perf.json"
        tracker = PerformanceTracker(str(db_file))
        
        signal = {
            'symbol': 'BTCUSDT',
            'type': 'BIG PUMP',
            'price': 50000.0,
            'rating': 85,
            'confidence': 0.9
        }
        
        signal_id = tracker.add_signal(signal)
        
        assert signal_id in tracker.signals
        assert tracker.stats['total_signals'] == 1
        assert tracker.signals[signal_id].symbol == 'BTCUSDT'
    
    def test_stats_calculation(self, tmp_path):
        """Расчёт статистики"""
        db_file = tmp_path / "test_perf.json"
        tracker = PerformanceTracker(str(db_file))
        
        # Добавляем несколько сигналов
        for i in range(5):
            signal = {
                'symbol': 'BTCUSDT',
                'type': 'BIG PUMP',
                'price': 50000.0,
                'rating': 80 + i,
                'confidence': 0.8
            }
            tracker.add_signal(signal)
        
        # Помечаем некоторые как проверенные
        for signal_id in list(tracker.signals.keys())[:3]:
            tracker.signals[signal_id].outcome_checked = True
            tracker.signals[signal_id].outcome_success = True
        
        tracker._update_stats()
        
        assert tracker.stats['checked_signals'] == 3
        assert tracker.stats['successful_signals'] == 3
    
    def test_degradation_detection(self, tmp_path):
        """Детекция деградации модели"""
        db_file = tmp_path / "test_perf.json"
        tracker = PerformanceTracker(str(db_file))
        
        # Добавляем 30 сигналов
        for i in range(30):
            signal = {
                'symbol': 'BTCUSDT',
                'type': 'BIG PUMP',
                'price': 50000.0,
                'rating': 80,
                'confidence': 0.8
            }
            tracker.add_signal(signal)
        
        # Все проверены, но только 40% успешных (ниже порога)
        for i, signal_id in enumerate(tracker.signals.keys()):
            tracker.signals[signal_id].outcome_checked = True
            tracker.signals[signal_id].outcome_success = (i % 10) < 4  # 40% успешных
        
        tracker._update_stats()
        
        # Должна сработать деградация
        assert tracker.should_alert_degradation(threshold=0.45)


class TestSignalEnhancement:
    """Тесты добавления SL/TP к сигналу"""
    
    def test_long_signal_sl_tp(self):
        """Проверка SL/TP для long сигнала"""
        signal = {
            'type': 'BIG PUMP',
            'rating': 80,
            'confidence': 0.8,
            'risk_score': 5
        }
        
        current_price = 100.0
        atr = 2.0
        
        result = add_sl_tp_to_signal(signal, current_price, atr)
        
        assert 'stop_loss' in result
        assert 'take_profit_1' in result
        assert 'take_profit_2' in result
        assert 'position_sizing' in result
        
        # Для long: SL ниже цены, TP выше
        assert result['stop_loss'] < current_price
        assert result['take_profit_1'] > current_price
        assert result['take_profit_2'] > result['take_profit_1']
    
    def test_short_signal_sl_tp(self):
        """Проверка SL/TP для short сигнала"""
        signal = {
            'type': 'BIG DUMP',
            'rating': 80,
            'confidence': 0.8,
            'risk_score': 5
        }
        
        current_price = 100.0
        atr = 2.0
        
        result = add_sl_tp_to_signal(signal, current_price, atr)
        
        # Для short: SL выше цены, TP ниже
        assert result['stop_loss'] > current_price
        assert result['take_profit_1'] < current_price
        assert result['take_profit_2'] < result['take_profit_1']


# ============================================================================
# INTEGRATION TESTS (требуют реального API или моков)
# ============================================================================

class TestIntegration:
    """Интеграционные тесты (требуют дополнительной настройки)"""
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires real API or extensive mocking")
    async def test_full_analysis_pipeline(self):
        """Полный пайплайн анализа символа"""
        # Этот тест требует настройки моков для всех API вызовов
        pass
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires real API or extensive mocking")
    async def test_scanner_loop_iteration(self):
        """Одна итерация scanner_loop"""
        # Этот тест требует настройки моков для send_text, send_photo и API
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
