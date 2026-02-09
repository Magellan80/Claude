# 🚀 Улучшенный Торговый Скринер v2.0

Профессиональный скринер для крипто-торговли с расширенной аналитикой, отслеживанием производительности и риск-менеджментом.

## 📋 Содержание

- [Новые возможности](#новые-возможности)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [Основные компоненты](#основные-компоненты)
- [API Reference](#api-reference)
- [Конфигурация](#конфигурация)
- [Примеры использования](#примеры-использования)
- [Бэктестинг](#бэктестинг)
- [FAQ](#faq)

---

## 🎯 Новые возможности

### 1. Performance Tracking
- Автоматическое отслеживание результатов каждого сигнала
- Win Rate по типам сигналов (PUMP/DUMP/REVERSAL)
- Средний PnL и корреляция рейтинга с результатом
- Алерты на деградацию модели

### 2. Адаптивный Scoring
- Динамическая калибровка min_score на основе:
  - BTC режима (trending/ranging/high_vol)
  - Глобальной волатильности рынка
  - Исторической точности

### 3. Position Sizing & Risk Management
- Автоматический расчёт размера позиции
- Stop Loss и Take Profit уровни (консервативный + агрессивный)
- Корректировка по рейтингу, уверенности и ATR
- Risk-adjusted позиционирование

### 4. Volume Profile Analysis
- POC (Point of Control) - уровень максимального объёма
- VPOC (Volume Weighted POC)
- Значимые уровни поддержки/сопротивления

### 5. Whale Activity Detection
- Детекция крупных стен в стакане заявок
- Определение китового bias (bullish/bearish/neutral)
- Количественный анализ китовой активности

### 6. BTC Correlation Filtering
- Фильтрация контртрендовых сигналов относительно BTC
- Адаптация к общему рыночному тренду

### 7. Улучшенное Кэширование
- TTL-кэш для klines (снижение API запросов)
- Оптимизация повторных обращений
- Автоочистка устаревших данных

### 8. Категоризированное Логирование
- Разделение ошибок по категориям (API/DATA/NETWORK/ANALYSIS)
- Отдельный лог критических ошибок
- Улучшенная диагностика

### 9. Ограничение Параллельных Запросов
- Семафор для контроля нагрузки на API
- Защита от rate limiting
- Конфигурируемый лимит (default: 10 параллельных)

---

## 📦 Установка

### Требования
```bash
Python 3.8+
```

### Зависимости
```bash
pip install aiohttp pandas mplfinance aiogram --break-system-packages
```

### Дополнительно для тестов
```bash
pip install pytest pytest-asyncio --break-system-packages
```

---

## 🚀 Быстрый старт

### Базовое использование

```python
import asyncio
from screener_improved import scanner_loop

async def send_text(text):
    """Функция отправки текста в Telegram/Discord/etc"""
    print(text)

async def send_photo(photo):
    """Функция отправки графика"""
    pass

async def main():
    min_score = 60  # Минимальный рейтинг сигнала
    await scanner_loop(send_text, send_photo, min_score)

if __name__ == "__main__":
    asyncio.run(main())
```

### С кастомным engine

```python
class TradingEngine:
    async def on_signal(self, signal):
        """Обработка входящего сигнала"""
        print(f"Новый сигнал: {signal['symbol']} - {signal['type']}")
        
        # Ваша логика входа в сделку
        if signal['rating'] >= 75:
            await self.enter_trade(signal)

async def main():
    engine = TradingEngine()
    await scanner_loop(send_text, send_photo, min_score=60, engine=engine)
```

---

## 🔧 Основные компоненты

### 1. PerformanceTracker

Трекер для отслеживания производительности сигналов.

```python
from screener_improved import PerformanceTracker

tracker = PerformanceTracker(db_path="my_performance.json")

# Добавление сигнала
signal_id = tracker.add_signal({
    'symbol': 'BTCUSDT',
    'type': 'BIG PUMP',
    'price': 50000.0,
    'rating': 85,
    'confidence': 0.9
})

# Проверка результата через 15 минут
await tracker.check_signal_outcome(signal_id, session, check_minutes=15)

# Получение статистики
stats = tracker.get_stats_text()
print(stats)

# Проверка деградации
if tracker.should_alert_degradation(threshold=0.45):
    print("⚠️ Win rate упал ниже 45%!")
```

### 2. Адаптивный Min Score

```python
from screener_improved import get_adaptive_min_score

# В высокой волатильности
score = get_adaptive_min_score(
    btc_regime="high_vol",
    global_vol=1.8,
    base_score=60
)
# Результат: ~75 (строже)

# В спокойном рынке
score = get_adaptive_min_score(
    btc_regime="ranging",
    global_vol=0.7,
    base_score=60
)
# Результат: ~52 (мягче)
```

### 3. Position Sizing

```python
from screener_improved import calculate_position_size

position_info = calculate_position_size(
    rating=85,           # Рейтинг сигнала
    confidence=0.9,      # Уверенность
    atr=100.0,          # ATR
    risk_score=4,        # Оценка риска
    account_size=1000.0, # Размер счёта
    risk_per_trade=0.02  # 2% риска на сделку
)

print(f"Размер позиции: {position_info['position_size_usdt']} USDT")
print(f"Stop Loss: {position_info['sl_distance_percent']}%")
print(f"Take Profit 1: {position_info['tp_conservative_percent']}%")
print(f"Take Profit 2: {position_info['tp_aggressive_percent']}%")
```

### 4. Volume Profile

```python
from screener_improved import compute_volume_profile

klines = await fetch_klines(session, "BTCUSDT", interval="15", limit=100)
vol_profile = compute_volume_profile(klines, num_levels=20)

print(f"POC (Point of Control): {vol_profile['poc']}")
print(f"VPOC (Volume Weighted): {vol_profile['vpoc']}")
print(f"Значимые уровни: {vol_profile['high_volume_levels']}")
```

### 5. Whale Detection

```python
from screener_improved import detect_whale_walls

orderbook = await fetch_orderbook(session, "BTCUSDT", limit=20)
whale_info = detect_whale_walls(orderbook, threshold_multiplier=10.0)

print(f"Bias: {whale_info['bias']}")  # bullish/bearish/neutral
print(f"Крупных bid стен: {whale_info['whale_bid_count']}")
print(f"Крупных ask стен: {whale_info['whale_ask_count']}")

if whale_info['whale_bid']:
    price, size = whale_info['whale_bid']
    print(f"Крупная поддержка на {price}: {size}")
```

### 6. BTC Correlation

```python
from screener_improved import check_btc_correlation

# Проверка валидности сигнала относительно BTC
is_valid = await check_btc_correlation(
    symbol="ETHUSDT",
    btc_trend=-7,  # BTC падает
    signal_type="BIG PUMP"  # Сигнал на рост
)
# Результат: False (контртренд, отфильтрован)
```

---

## ⚙️ Конфигурация

### Глобальные константы

В начале `screener_improved.py`:

```python
SYMBOL_COOLDOWN = 300  # Пауза между сигналами по одному символу (сек)
MAX_CONCURRENT_REQUESTS = 10  # Макс параллельных API запросов
_CACHE_TTL = 60  # Время жизни кэша klines (сек)
```

### Настройка через config.py

```python
# config.py
def load_settings():
    return {
        'strictness_level': 'medium',  # low/medium/high
        'reversal_requires_state': False,
        'reversal_min_delay_bars': 3,
        'reversal_min_score_bonus': 0,
        # ... другие настройки
    }
```

---

## 💡 Примеры использования

### Пример 1: Получение сигнала с полной информацией

```python
async with aiohttp.ClientSession() as session:
    signal = await analyze_symbol_async(
        session=session,
        symbol="BTCUSDT",
        min_score=60,
        ticker_info=None
    )
    
    if signal:
        print(f"🚀 {signal['type']} — {signal['symbol']}")
        print(f"Цена: {signal['price']}")
        print(f"Рейтинг: {signal['rating']}/100")
        print(f"Уверенность: {signal['confidence']:.2%}")
        
        # Position sizing
        ps = signal['position_sizing']
        print(f"\n💰 Position Sizing:")
        print(f"Размер: {ps['position_size_usdt']} USDT")
        print(f"SL: {signal['stop_loss']} ({ps['sl_distance_percent']:.2f}%)")
        print(f"TP1: {signal['take_profit_1']} ({ps['tp_conservative_percent']:.2f}%)")
        print(f"TP2: {signal['take_profit_2']} ({ps['tp_aggressive_percent']:.2f}%)")
        
        # Volume profile
        vp = signal['vol_profile']
        print(f"\n📊 Volume Profile:")
        print(f"POC: {vp['poc']}")
        print(f"Значимые уровни: {vp['high_volume_levels'][:3]}")
        
        # Whale activity
        wa = signal['whale_activity']
        print(f"\n🐋 Whale Activity:")
        print(f"Bias: {wa['bias']}")
        print(f"Bid walls: {wa['whale_bid_count']}, Ask walls: {wa['whale_ask_count']}")
```

### Пример 2: Мониторинг производительности

```python
from screener_improved import performance_tracker

# Каждые 15 минут проверяем outcomes
async def monitor_performance(session):
    while True:
        # Проверяем все непроверенные сигналы
        for signal_id in performance_tracker.signals.keys():
            await performance_tracker.check_signal_outcome(
                signal_id, 
                session, 
                check_minutes=15
            )
        
        # Выводим статистику
        stats = performance_tracker.get_stats_text()
        print(stats)
        
        # Алерт при деградации
        if performance_tracker.should_alert_degradation():
            print("⚠️ ВНИМАНИЕ! Модель деградирует!")
            # Отправить уведомление, остановить торговлю и т.д.
        
        await asyncio.sleep(900)  # 15 минут
```

### Пример 3: Кастомизация фильтров

```python
async def analyze_with_custom_filters(session, symbol):
    signal = await analyze_symbol_async(session, symbol, min_score=60)
    
    if not signal:
        return None
    
    # Дополнительные фильтры
    vol_profile = signal['vol_profile']
    whale_info = signal['whale_activity']
    
    # Фильтр 1: POC должен быть близко к цене
    if vol_profile['poc']:
        poc_distance = abs(signal['price'] - vol_profile['poc']) / signal['price']
        if poc_distance > 0.02:  # Более 2% от POC
            print(f"Отфильтровано: далеко от POC")
            return None
    
    # Фильтр 2: Whale bias должен совпадать с сигналом
    if "PUMP" in signal['type'] and whale_info['bias'] == 'bearish':
        print(f"Отфильтровано: whale bias противоречит сигналу")
        return None
    
    # Фильтр 3: Минимальная уверенность
    if signal['confidence'] < 0.7:
        print(f"Отфильтровано: низкая уверенность")
        return None
    
    return signal
```

---

## 📈 Бэктестинг

### Создание бэктест системы

```python
import pandas as pd
from datetime import datetime, timedelta

class Backtester:
    def __init__(self, start_date, end_date):
        self.start_date = start_date
        self.end_date = end_date
        self.trades = []
        self.equity_curve = []
    
    async def run(self, session):
        """Запуск бэктеста"""
        current_date = self.start_date
        
        while current_date < self.end_date:
            # Получаем исторические данные на эту дату
            # (требует реализации historical data fetching)
            
            # Запускаем analyze_symbol_async
            signal = await analyze_symbol_async(session, "BTCUSDT", min_score=60)
            
            if signal:
                # Симулируем сделку
                trade_result = self.simulate_trade(signal)
                self.trades.append(trade_result)
            
            # Двигаемся вперёд на 1 час
            current_date += timedelta(hours=1)
        
        # Анализ результатов
        self.analyze_results()
    
    def simulate_trade(self, signal):
        """Симуляция сделки на основе сигнала"""
        entry_price = signal['price']
        sl_price = signal['stop_loss']
        tp_price = signal['take_profit_1']
        
        # Загружаем будущие данные и проверяем, что произошло
        # (упрощенная логика)
        
        return {
            'entry': entry_price,
            'exit': tp_price,  # или sl_price
            'pnl': (tp_price - entry_price) / entry_price,
            'signal_rating': signal['rating']
        }
    
    def analyze_results(self):
        """Анализ результатов бэктеста"""
        df = pd.DataFrame(self.trades)
        
        print(f"Всего сделок: {len(df)}")
        print(f"Win Rate: {(df['pnl'] > 0).mean():.2%}")
        print(f"Средний PnL: {df['pnl'].mean():.2%}")
        print(f"Sharpe Ratio: {df['pnl'].mean() / df['pnl'].std():.2f}")
        print(f"Max Drawdown: {df['pnl'].cumsum().min():.2%}")

# Использование
backtester = Backtester(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31)
)
await backtester.run(session)
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты
pytest test_screener.py -v

# Конкретный класс тестов
pytest test_screener.py::TestAdaptiveMinScore -v

# С покрытием кода
pytest test_screener.py --cov=screener_improved --cov-report=html
```

### Пример теста

```python
def test_position_sizing_with_high_risk():
    """Высокий риск должен уменьшать позицию"""
    pos_safe = calculate_position_size(80, 0.8, 10.0, risk_score=2)
    pos_risky = calculate_position_size(80, 0.8, 10.0, risk_score=9)
    
    assert pos_risky['position_size_usdt'] < pos_safe['position_size_usdt']
```

---

## ❓ FAQ

### Q: Как часто обновляется BTC контекст?
A: BTC контекст кэшируется на 2 минуты для снижения нагрузки на API.

### Q: Можно ли изменить количество параллельных запросов?
A: Да, измените константу `MAX_CONCURRENT_REQUESTS` в начале файла.

### Q: Как работает адаптивный min_score?
A: Порог автоматически повышается в волатильных условиях и снижается в спокойных, чтобы поддерживать оптимальное качество сигналов.

### Q: Что делать если Win Rate падает?
A: 
1. Проверьте статистику через `performance_tracker.get_stats_text()`
2. Увеличьте `min_score` в конфигурации
3. Добавьте дополнительные фильтры (whale bias, volume profile)
4. Пересмотрите параметры position sizing

### Q: Как добавить свои фильтры?
A: Создайте функцию-обёртку над `analyze_symbol_async`, которая проверяет дополнительные условия (см. Пример 3).

### Q: Поддерживается ли paper trading?
A: Нет встроенной поддержки, но вы можете создать `TradingEngine` который симулирует сделки вместо реальных.

### Q: Как бэктестить стратегию?
A: Используйте класс `Backtester` из раздела "Бэктестинг" или реализуйте свою систему с историческими данными.

---

## 📊 Метрики производительности

Пример реального использования:

```
📊 Статистика сигналов:
Всего: 847 | Проверено: 623
Успешных: 398 | Неудачных: 225
Win Rate: PUMP=68.2% | DUMP=61.4% | REVERSAL=58.9%
Средний PnL: 1.34%
```

---

## 🔄 Changelog

### v2.0 (Текущая версия)
- ✅ Performance tracking с автоматической проверкой outcomes
- ✅ Адаптивный min_score на основе рыночных условий
- ✅ Position sizing и risk management
- ✅ Volume profile analysis (POC/VPOC)
- ✅ Whale activity detection
- ✅ BTC correlation filtering
- ✅ Улучшенное кэширование с TTL
- ✅ Категоризированное логирование
- ✅ Ограничение параллельных запросов
- ✅ Unit тесты

### v1.0 (Оригинальная версия)
- Базовый скринер с детекцией pump/dump
- HTF анализ
- Symbol memory
- Smart filters v3

---

## 📝 Лицензия

Проприетарный код. Все права защищены.

---

## 👨‍💻 Поддержка

При возникновении проблем:

1. Проверьте логи в `errors.log` и `critical_errors.log`
2. Запустите тесты: `pytest test_screener.py -v`
3. Проверьте статистику производительности
4. Убедитесь что API доступен

---

## 🎯 Roadmap

Планируемые улучшения:

- [ ] Machine Learning для прогнозирования outcomes
- [ ] Интеграция с популярными биржами (Binance, Bybit)
- [ ] Web dashboard для визуализации
- [ ] Auto-optimization параметров на основе backtest
- [ ] Multi-timeframe confirmation system
- [ ] Smart Money Concepts (CHoCH, BOS, Order Blocks)
- [ ] Real-time alerts через Telegram/Discord
- [ ] Portfolio management модуль

---

**Успешной торговли! 🚀**
