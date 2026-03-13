import io
import os
import time
import asyncio
import datetime
import aiohttp

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.exceptions import TelegramRetryAfter, TelegramNetworkError, TelegramServerError
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))


class TelegramNotifier:
    def __init__(self, token: str, chat_id: int):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.chat_id = chat_id

        # флаги
        self.signals_enabled = True
        self.trading_enabled = False

        # состояние сигналов
        self.last_direction = {}
        self.last_quality = {}

        # кэш фандинга
        self._funding_cache = {}
        self._funding_ttl = 60

        # aiohttp session
        self._session: aiohttp.ClientSession | None = None

        # кнопки
        self.dp.callback_query.register(self.cb_toggle_signals, F.data == "toggle_signals")
        self.dp.callback_query.register(self.cb_mode_screener, F.data == "mode_screener")
        self.dp.callback_query.register(self.cb_mode_trading, F.data == "mode_trading")
        self.dp.callback_query.register(self.cb_status, F.data == "status")

    # ============================================================
    #   КНОПКИ
    # ============================================================

    def main_menu(self):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Включить/Выключить сигналы", callback_data="toggle_signals")],
            [InlineKeyboardButton(text="🔍 Режим скринера", callback_data="mode_screener")],
            [InlineKeyboardButton(text="🤖 Режим торговли", callback_data="mode_trading")],
            [InlineKeyboardButton(text="📊 Статус", callback_data="status")],
        ])
        return kb

    async def cb_toggle_signals(self, call: types.CallbackQuery):
        try:
            await call.answer()
        except:
            pass

        self.signals_enabled = not self.signals_enabled
        state = "🟢 включены" if self.signals_enabled else "🔴 выключены"
        await call.message.edit_text(f"Сигналы теперь {state}", reply_markup=self.main_menu())

    async def cb_mode_screener(self, call: types.CallbackQuery):
        try:
            await call.answer()
        except:
            pass

        self.trading_enabled = False
        await call.message.edit_text("🔍 Режим скринера активирован", reply_markup=self.main_menu())

    async def cb_mode_trading(self, call: types.CallbackQuery):
        try:
            await call.answer()
        except:
            pass

        self.trading_enabled = True
        await call.message.edit_text("🤖 Режим торговли активирован", reply_markup=self.main_menu())

    async def cb_status(self, call: types.CallbackQuery):
        try:
            await call.answer()
        except:
            pass

        s1 = "🟢 ВКЛ" if self.signals_enabled else "🔴 ВЫКЛ"
        s2 = "🤖 Торговля" if self.trading_enabled else "🔍 Скринер"

        new_text = (
            f"Статус:\n\n"
            f"Сигналы: {s1}\n"
            f"Режим: {s2}\n"
        )

        if call.message.text == new_text:
            return

        await call.message.edit_text(new_text, reply_markup=self.main_menu())

    # ============================================================
    #   БЕЗОПАСНАЯ ОТПРАВКА
    # ============================================================

    async def safe_send_message(self, text: str):
        delay = 1
        for attempt in range(10):
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text[:4096],
                    reply_markup=self.main_menu()
                )
                return
            except TelegramRetryAfter as e:
                print(f"[TG] Rate limit, waiting {e.retry_after}s")
                await asyncio.sleep(e.retry_after)
            except (TelegramNetworkError, TelegramServerError) as e:
                print(f"[TG] Network/Server error (attempt {attempt+1}): {e}")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
            except Exception as e:
                print(f"[TG] safe_send_message FAILED: {type(e).__name__}: {e}")
                return

    async def safe_send_photo(self, photo_bytes: bytes, caption: str):
        delay = 1
        # aiogram 3.x требует BufferedInputFile вместо raw bytes
        photo_file = BufferedInputFile(photo_bytes, filename="chart.png")
        for attempt in range(10):
            try:
                await self.bot.send_photo(
                    chat_id=self.chat_id,
                    photo=photo_file,
                    caption=caption[:1024],
                    reply_markup=self.main_menu()
                )
                return
            except TelegramRetryAfter as e:
                print(f"[TG] Rate limit, waiting {e.retry_after}s")
                await asyncio.sleep(e.retry_after)
            except (TelegramNetworkError, TelegramServerError) as e:
                print(f"[TG] Network/Server error (attempt {attempt+1}): {e}")
                # Пересоздаём объект файла при повторе
                photo_file = BufferedInputFile(photo_bytes, filename="chart.png")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
            except Exception as e:
                print(f"[TG] safe_send_photo FAILED: {type(e).__name__}: {e}")
                # Фото не отправилось — пробуем отправить текстом
                await self.safe_send_message(caption)
                return

    # ============================================================
    #   ФАНДИНГ
    # ============================================================

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _fetch_funding(self, symbol: str) -> float:
        url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
        try:
            session = await self._get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                data = await resp.json()
                funding = float(data["result"]["list"][0]["fundingRate"])
                return funding * 100
        except Exception as e:
            print(f"[TG] Funding fetch error for {symbol}: {e}")
            return 0.0

    async def get_funding(self, symbol: str) -> float:
        now = time.time()
        cached = self._funding_cache.get(symbol)

        if cached:
            ts, value = cached
            if now - ts < self._funding_ttl:
                return value

        value = await self._fetch_funding(symbol)
        self._funding_cache[symbol] = (now, value)
        return value

    def funding_color(self, f: float) -> str:
        if abs(f) < 0.01:
            return "🟢"
        if abs(f) < 0.03:
            return "🟠"
        return "🔴"

    # ============================================================
    #   ГРАФИК 15m
    # ============================================================

    def _make_chart_sync(self, candles):
        if not candles or len(candles) < 10:
            return None

        try:
            fig, ax = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={"height_ratios": [3, 1]})

            times = [datetime.datetime.fromtimestamp(c["timestamp"] / 1000) for c in candles]
            opens = [c["open"] for c in candles]
            highs = [c["high"] for c in candles]
            lows = [c["low"] for c in candles]
            closes = [c["close"] for c in candles]
            volumes = [c["volume"] for c in candles]

            for i in range(len(candles)):
                color = "green" if closes[i] >= opens[i] else "red"
                ax[0].plot([times[i], times[i]], [lows[i], highs[i]], color=color)
                ax[0].plot([times[i], times[i]], [opens[i], closes[i]], color=color, linewidth=4)

            ax[0].set_title("15m Chart")
            ax[0].grid(True)

            ax[1].bar(times, volumes, color="blue", alpha=0.4)
            ax[1].set_title("Volume")
            ax[1].grid(True)

            fig.autofmt_xdate()
            buf = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()
        except Exception as e:
            print(f"[TG] Chart generation error: {e}")
            return None

    async def make_chart(self, candles):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._make_chart_sync, candles)

    # ============================================================
    #   ОТПРАВКА СИГНАЛА
    # ============================================================

    async def send_signal(self, symbol: str, direction: str, signal_type: str,
                          price: float, quality: int, htf_regime: str,
                          candles_15m):

        if not self.signals_enabled:
            print(f"[TG] Signal skipped (signals disabled): {symbol}")
            return

        direction = direction.lower()
        new_dir = "Long" if direction == "long" else "Short"
        color = "🟢" if direction == "long" else "🔴"

        funding = await self.get_funding(symbol)
        f_color = self.funding_color(funding)

        prev_dir = self.last_direction.get(symbol)
        prev_q = self.last_quality.get(symbol, -1)

        if prev_dir is None:
            header = f"{color}{symbol} {signal_type} {new_dir}"
        else:
            if prev_dir != direction:
                old = "Long" if prev_dir == "long" else "Short"
                header = f"{color}{symbol} {signal_type} {old} → {new_dir}"
            else:
                if quality <= prev_q:
                    print(f"[TG] Signal skipped (quality not improved): {symbol} {direction} q={quality} prev_q={prev_q}")
                    return
                header = f"{color}{symbol} {signal_type} {new_dir} (↑ качество)"

        self.last_direction[symbol] = direction
        self.last_quality[symbol] = quality

        text = (
            f"{header}\n\n"
            f"Цена: {price}\n"
            f"Сила сигнала: {quality}/100\n"
            f"Фандинг: {f_color} {funding:.4f}%\n"
            f"HTF: {htf_regime}\n"
        )

        print(f"[TG] Sending signal: {symbol} {direction} q={quality}")

        if not candles_15m or len(candles_15m) < 20:
            await self.safe_send_message(text)
            return

        chart_bytes = await self.make_chart(candles_15m)
        if chart_bytes is None:
            await self.safe_send_message(text)
            return

        await self.safe_send_photo(chart_bytes, text)

    # ============================================================
    #   ПОЛЛИНГ
    # ============================================================

    async def run(self):
        print("[TG] polling started")
        await self.safe_send_message("Telegram бот запущен")

        # polling НЕ блокирует event loop
        asyncio.create_task(self.dp.start_polling(self.bot))

        last_tg_heartbeat = time.time()

        try:
            while True:
                if time.time() - last_tg_heartbeat > 30:
                    print(f"[TG] alive {datetime.datetime.now().strftime('%H:%M:%S')}")
                    last_tg_heartbeat = time.time()

                await asyncio.sleep(1)

        finally:
            if self._session and not self._session.closed:
                await self._session.close()
