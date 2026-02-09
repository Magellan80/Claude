# 🚀 Quick Start Guide - Улучшенный Скринер

## За 5 минут до первого запуска

### Шаг 1: Установка зависимостей

```bash
pip install -r requirements.txt --break-system-packages
```

### Шаг 2: Копирование конфигурации

```bash
cp config_example.py config.py
```

Откройте `config.py` и настройте:
- `ACCOUNT_SIZE_USDT` - размер вашего счёта
- `RISK_PER_TRADE` - риск на сделку (рекомендуется 0.01-0.02)
- `BASE_MIN_SCORE` - минимальный рейтинг сигнала (60 по умолчанию)

### Шаг 3: Создание базового бота

Создайте файл `bot.py`:

```python
import asyncio
from screener_improved import scanner_loop

# Простая заглушка для вывода в консоль
async def send_text(text):
    print(text)
    print("-" * 80)

async def send_photo(photo):
    print("📊 График отправлен")

async def main():
    print("🚀 Запуск скринера...")
    print("Нажмите Ctrl+C для остановки")
    
    try:
        await scanner_loop(
            send_text=send_text,
            send_photo=send_photo,
            min_score=60
        )
    except KeyboardInterrupt:
        print("\n✅ Скринер остановлен")

if __name__ == "__main__":
    asyncio.run(main())
```

### Шаг 4: Запуск

```bash
python bot.py
```

Готово! Скринер начнёт анализировать рынок и выводить сигналы в консоль.

---

## Интеграция с Telegram

### Вариант 1: Простой бот

```python
import asyncio
from aiogram import Bot, Dispatcher
from screener_improved import scanner_loop

# Ваш токен бота
BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"  # ID чата для уведомлений

bot = Bot(token=BOT_TOKEN)

async def send_text(text):
    """Отправка текста в Telegram"""
    await bot.send_message(chat_id=CHAT_ID, text=text)

async def send_photo(photo):
    """Отправка графика в Telegram"""
    await bot.send_photo(chat_id=CHAT_ID, photo=photo)

async def main():
    print("🤖 Telegram бот запущен...")
    
    await scanner_loop(
        send_text=send_text,
        send_photo=send_photo,
        min_score=60
    )

if __name__ == "__main__":
    asyncio.run(main())
```

### Вариант 2: С командами и статистикой

```python
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from screener_improved import scanner_loop, performance_tracker

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def send_text(text):
    await bot.send_message(chat_id=CHAT_ID, text=text)

async def send_photo(photo):
    await bot.send_photo(chat_id=CHAT_ID, photo=photo)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Команда /stats - показать статистику"""
    stats = performance_tracker.get_stats_text()
    await message.answer(stats)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🚀 Скринер запущен!\n"
        "Используй /stats для просмотра статистики"
    )

async def main():
    # Запускаем бота и скринер параллельно
    await asyncio.gather(
        dp.start_polling(bot),
        scanner_loop(send_text, send_photo, min_score=60)
    )

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Первая торговая стратегия

### Консервативная стратегия

```python
from screener_improved import scanner_loop

class ConservativeEngine:
    """Консервативный торговый движок"""
    
    async def on_signal(self, signal):
        """Обработка сигнала"""
        
        # Фильтр 1: Высокий рейтинг
        if signal['rating'] < 75:
            return
        
        # Фильтр 2: Высокая уверенность
        if signal['confidence'] < 0.8:
            return
        
        # Фильтр 3: Низкий риск
        if signal['risk_score'] > 5:
            return
        
        # Фильтр 4: Whale bias совпадает
        whale_bias = signal['whale_activity']['bias']
        if "PUMP" in signal['type'] and whale_bias == 'bearish':
            return
        if "DUMP" in signal['type'] and whale_bias == 'bullish':
            return
        
        # Все фильтры пройдены - входим в сделку
        await self.enter_trade(signal)
    
    async def enter_trade(self, signal):
        """Вход в сделку"""
        print(f"✅ ВХОД В СДЕЛКУ: {signal['symbol']}")
        print(f"   Тип: {signal['type']}")
        print(f"   Цена входа: {signal['price']}")
        print(f"   Stop Loss: {signal['stop_loss']}")
        print(f"   Take Profit 1: {signal['take_profit_1']}")
        print(f"   Размер позиции: {signal['position_sizing']['position_size_usdt']} USDT")
        
        # Здесь ваша логика размещения ордеров на бирже

# Использование
async def main():
    engine = ConservativeEngine()
    await scanner_loop(send_text, send_photo, min_score=60, engine=engine)
```

### Агрессивная стратегия

```python
class AggressiveEngine:
    """Агрессивный торговый движок"""
    
    async def on_signal(self, signal):
        # Менее строгие фильтры
        if signal['rating'] < 65 or signal['confidence'] < 0.6:
            return
        
        # Больше позиция в хороших сигналах
        position_multiplier = 1.0
        if signal['rating'] >= 85:
            position_multiplier = 1.5
        
        # Агрессивный TP
        tp = signal['take_profit_2']  # Используем агрессивный TP
        
        await self.enter_trade(signal, position_multiplier, tp)
    
    async def enter_trade(self, signal, multiplier, tp):
        position_size = signal['position_sizing']['position_size_usdt'] * multiplier
        
        print(f"🔥 АГРЕССИВНЫЙ ВХОД: {signal['symbol']}")
        print(f"   Размер: {position_size} USDT (x{multiplier})")
        print(f"   TP: {tp}")
```

---

## Мониторинг производительности

### Автоматический мониторинг

```python
import asyncio
from screener_improved import performance_tracker

async def monitor_loop():
    """Мониторинг каждые 30 минут"""
    while True:
        await asyncio.sleep(1800)  # 30 минут
        
        stats = performance_tracker.get_stats_text()
        print("\n" + "="*80)
        print(stats)
        print("="*80 + "\n")
        
        # Алерт при деградации
        if performance_tracker.should_alert_degradation():
            print("⚠️ КРИТИЧНО! Win rate упал ниже 45%!")
            print("Рекомендуется:")
            print("  1. Повысить min_score до 70-75")
            print("  2. Добавить дополнительные фильтры")
            print("  3. Временно приостановить автоматическую торговлю")

# Запуск параллельно со скринером
async def main():
    await asyncio.gather(
        scanner_loop(send_text, send_photo, min_score=60),
        monitor_loop()
    )
```

### Экспорт статистики в CSV

```python
import pandas as pd
from screener_improved import performance_tracker

def export_to_csv():
    """Экспорт всех сигналов в CSV для анализа"""
    
    data = []
    for signal_id, signal in performance_tracker.signals.items():
        data.append({
            'signal_id': signal_id,
            'symbol': signal.symbol,
            'type': signal.signal_type,
            'entry_price': signal.entry_price,
            'rating': signal.rating,
            'confidence': signal.confidence,
            'outcome_success': signal.outcome_success,
            'pnl_percent': signal.pnl_percent,
            'timestamp': signal.timestamp
        })
    
    df = pd.DataFrame(data)
    df.to_csv('signal_history.csv', index=False)
    print(f"✅ Экспортировано {len(df)} сигналов в signal_history.csv")

# Вызывать периодически
export_to_csv()
```

---

## Часто встречающиеся проблемы

### Проблема 1: "Rate limit exceeded"

**Решение:**
```python
# В config.py уменьшите количество параллельных запросов:
MAX_CONCURRENT_API_REQUESTS = 5

# И увеличьте интервал сканирования:
SCAN_INTERVAL_SECONDS = 60  # вместо 30
```

### Проблема 2: Слишком много сигналов

**Решение:**
```python
# Повысьте min_score:
await scanner_loop(send_text, send_photo, min_score=70)

# Или добавьте фильтр в engine:
async def on_signal(self, signal):
    if signal['confidence'] < 0.85:  # Только очень уверенные
        return
```

### Проблема 3: Мало сигналов

**Решение:**
```python
# Понизьте min_score:
await scanner_loop(send_text, send_photo, min_score=50)

# Или отключите некоторые фильтры в config.py:
ENABLE_BTC_CORRELATION_FILTER = False
STRICTNESS_LEVEL = "low"
```

### Проблема 4: Низкий Win Rate

**Решение:**
1. Проверьте `signal_performance.json` - какие типы сигналов работают хуже
2. Добавьте фильтры для слабых типов
3. Увеличьте `MIN_CONFIDENCE_FOR_ENTRY`
4. Проверьте параметры position sizing

---

## Следующие шаги

После успешного запуска:

1. **Запустите на paper trading** - протестируйте стратегию без реальных денег
2. **Собирайте статистику** - минимум 100 сигналов для анализа
3. **Оптимизируйте параметры** - на основе real performance
4. **Добавьте свои фильтры** - под ваш стиль торговли
5. **Интегрируйте с биржей** - начинайте с минимальных сумм

---

## Поддержка

Если что-то не работает:

1. Проверьте `errors.log`
2. Запустите `pytest test_screener.py -v`
3. Убедитесь что все зависимости установлены
4. Проверьте доступность API Binance

**Успехов в трейдинге! 📈**
