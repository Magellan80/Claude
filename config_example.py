"""
Пример файла конфигурации для улучшенного скринера
Скопируйте в config.py и настройте под себя
"""

# ============================================================================
# ОСНОВНЫЕ НАСТРОЙКИ
# ============================================================================

# Режим работы
CURRENT_MODE = "production"  # production / testing / backtesting

# Минимальный рейтинг сигнала (будет автоматически адаптироваться)
BASE_MIN_SCORE = 60

# Cooldown между сигналами по одному символу (секунды)
SYMBOL_COOLDOWN_SECONDS = 300  # 5 минут

# Максимальное количество параллельных API запросов
MAX_CONCURRENT_API_REQUESTS = 10

# TTL для кэша klines (секунды)
KLINES_CACHE_TTL = 60

# ============================================================================
# PERFORMANCE TRACKING
# ============================================================================

# Путь к файлу с данными о производительности
PERFORMANCE_DB_PATH = "signal_performance.json"

# Через сколько минут проверять результат сигнала
SIGNAL_OUTCOME_CHECK_MINUTES = 15

# Минимальный win rate перед алертом о деградации
MIN_WIN_RATE_THRESHOLD = 0.45  # 45%

# Минимальное количество проверенных сигналов перед алертами
MIN_SIGNALS_FOR_STATS = 20

# Частота проверки outcomes и отправки статистики (итерации scanner_loop)
STATS_UPDATE_FREQUENCY = 10  # каждые 10 итераций

# ============================================================================
# POSITION SIZING & RISK MANAGEMENT
# ============================================================================

# Размер торгового счёта в USDT (для расчёта position sizing)
ACCOUNT_SIZE_USDT = 1000.0

# Риск на одну сделку (процент от счёта)
RISK_PER_TRADE = 0.02  # 2%

# Множитель ATR для Stop Loss
ATR_MULTIPLIER_SL = 1.5

# Множители ATR для Take Profit
ATR_MULTIPLIER_TP_CONSERVATIVE = 3.0
ATR_MULTIPLIER_TP_AGGRESSIVE = 4.5

# Минимальная уверенность для входа в сделку
MIN_CONFIDENCE_FOR_ENTRY = 0.7

# ============================================================================
# ФИЛЬТРЫ И ДЕТЕКТОРЫ
# ============================================================================

# Уровень строгости фильтров
STRICTNESS_LEVEL = "medium"  # low / medium / high

# Требовать определённого состояния для реверсалов
REVERSAL_REQUIRES_STATE = False

# Минимальная задержка между барами для реверсала
REVERSAL_MIN_DELAY_BARS = 3

# Бонус к минимальному score для реверсалов
REVERSAL_MIN_SCORE_BONUS = 0

# Минимальная волатильность для BTC (high_vol режим)
BTC_HIGH_VOL_THRESHOLD = 0.005  # 0.5%

# Пороги для BTC trending режима
BTC_STRONG_TREND_THRESHOLD = 5  # abs(trend_score) > 5

# Пороги для BTC ranging режима
BTC_RANGING_THRESHOLD = 2  # abs(trend_score) < 2

# ============================================================================
# VOLUME PROFILE
# ============================================================================

# Количество уровней для volume profile
VOLUME_PROFILE_LEVELS = 20

# Топ N уровней с высоким объёмом для анализа
VOLUME_PROFILE_TOP_LEVELS = 5

# ============================================================================
# WHALE DETECTION
# ============================================================================

# Во сколько раз ордер должен быть больше среднего для whale статуса
WHALE_THRESHOLD_MULTIPLIER = 10.0

# Сколько топ ордеров анализировать из orderbook
WHALE_ORDERBOOK_DEPTH = 20

# Минимальное соотношение whale объёмов для определения bias
WHALE_BIAS_RATIO = 1.5  # 1.5x больше в одну сторону

# ============================================================================
# BTC CORRELATION
# ============================================================================

# Фильтровать ли контртрендовые сигналы относительно BTC
ENABLE_BTC_CORRELATION_FILTER = True

# Порог BTC тренда для фильтрации (abs value)
BTC_CORRELATION_TREND_THRESHOLD = 5

# TTL для BTC контекста (секунды)
BTC_CONTEXT_CACHE_TTL = 120  # 2 минуты

# ============================================================================
# ЛОГИРОВАНИЕ
# ============================================================================

# Пути к файлам логов
SIGNALS_LOG_PATH = "signals.log"
ERRORS_LOG_PATH = "errors.log"
CRITICAL_ERRORS_LOG_PATH = "critical_errors.log"

# Максимальный размер лог файла перед ротацией (байты)
MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Количество старых лог файлов для хранения
LOG_BACKUP_COUNT = 5

# ============================================================================
# API И ИНТЕРВАЛЫ
# ============================================================================

# Таймфреймы для анализа
TIMEFRAMES = {
    "1m": "1",
    "15m": "15",
    "1h": "60",
    "4h": "240"
}

# Лимиты klines для каждого таймфрейма
KLINES_LIMITS = {
    "1m": 120,
    "15m": 96,
    "1h": 96,
    "4h": 96
}

# Интервал сканирования (секунды)
SCAN_INTERVAL_SECONDS = 30

# Timeout для API запросов (секунды)
API_REQUEST_TIMEOUT = 10

# Количество retry при ошибках API
API_MAX_RETRIES = 3

# Задержка между retry (секунды)
API_RETRY_DELAY = 5

# ============================================================================
# УВЕДОМЛЕНИЯ
# ============================================================================

# Отправлять ли уведомления при деградации модели
ENABLE_DEGRADATION_ALERTS = True

# Отправлять ли статистику периодически
ENABLE_PERIODIC_STATS = True

# Максимальное количество топ сигналов для отправки за итерацию
MAX_SIGNALS_PER_ITERATION = 10

# Отправлять ли графики свечей
ENABLE_CANDLE_CHARTS = True

# ============================================================================
# ЭКСПЕРИМЕНТАЛЬНЫЕ ФИЧИ
# ============================================================================

# Использовать ML модель для предсказания outcomes (требует обучения)
ENABLE_ML_PREDICTIONS = False

# Автоматическая оптимизация параметров на основе backtest
ENABLE_AUTO_OPTIMIZATION = False

# Smart Money Concepts анализ
ENABLE_SMC_ANALYSIS = False

# ============================================================================
# ФУНКЦИИ ЗАГРУЗКИ КОНФИГУРАЦИИ
# ============================================================================

def get_current_mode():
    """Получить текущий режим работы"""
    return CURRENT_MODE


def load_settings():
    """Загрузить все настройки в виде словаря"""
    return {
        # Основные
        'base_min_score': BASE_MIN_SCORE,
        'symbol_cooldown': SYMBOL_COOLDOWN_SECONDS,
        'max_concurrent_requests': MAX_CONCURRENT_API_REQUESTS,
        'cache_ttl': KLINES_CACHE_TTL,
        
        # Performance
        'performance_db': PERFORMANCE_DB_PATH,
        'outcome_check_minutes': SIGNAL_OUTCOME_CHECK_MINUTES,
        'min_win_rate': MIN_WIN_RATE_THRESHOLD,
        'min_signals_for_stats': MIN_SIGNALS_FOR_STATS,
        'stats_frequency': STATS_UPDATE_FREQUENCY,
        
        # Risk Management
        'account_size': ACCOUNT_SIZE_USDT,
        'risk_per_trade': RISK_PER_TRADE,
        'atr_sl': ATR_MULTIPLIER_SL,
        'atr_tp_conservative': ATR_MULTIPLIER_TP_CONSERVATIVE,
        'atr_tp_aggressive': ATR_MULTIPLIER_TP_AGGRESSIVE,
        'min_confidence': MIN_CONFIDENCE_FOR_ENTRY,
        
        # Фильтры
        'strictness_level': STRICTNESS_LEVEL,
        'reversal_requires_state': REVERSAL_REQUIRES_STATE,
        'reversal_min_delay_bars': REVERSAL_MIN_DELAY_BARS,
        'reversal_min_score_bonus': REVERSAL_MIN_SCORE_BONUS,
        
        # BTC
        'btc_high_vol': BTC_HIGH_VOL_THRESHOLD,
        'btc_strong_trend': BTC_STRONG_TREND_THRESHOLD,
        'btc_ranging': BTC_RANGING_THRESHOLD,
        'btc_correlation_enabled': ENABLE_BTC_CORRELATION_FILTER,
        'btc_correlation_threshold': BTC_CORRELATION_TREND_THRESHOLD,
        'btc_cache_ttl': BTC_CONTEXT_CACHE_TTL,
        
        # Volume Profile
        'vol_profile_levels': VOLUME_PROFILE_LEVELS,
        'vol_profile_top': VOLUME_PROFILE_TOP_LEVELS,
        
        # Whale
        'whale_threshold': WHALE_THRESHOLD_MULTIPLIER,
        'whale_depth': WHALE_ORDERBOOK_DEPTH,
        'whale_bias_ratio': WHALE_BIAS_RATIO,
        
        # Logs
        'signals_log': SIGNALS_LOG_PATH,
        'errors_log': ERRORS_LOG_PATH,
        'critical_log': CRITICAL_ERRORS_LOG_PATH,
        
        # API
        'timeframes': TIMEFRAMES,
        'klines_limits': KLINES_LIMITS,
        'scan_interval': SCAN_INTERVAL_SECONDS,
        'api_timeout': API_REQUEST_TIMEOUT,
        'api_retries': API_MAX_RETRIES,
        'api_retry_delay': API_RETRY_DELAY,
        
        # Уведомления
        'degradation_alerts': ENABLE_DEGRADATION_ALERTS,
        'periodic_stats': ENABLE_PERIODIC_STATS,
        'max_signals': MAX_SIGNALS_PER_ITERATION,
        'enable_charts': ENABLE_CANDLE_CHARTS,
        
        # Experimental
        'ml_predictions': ENABLE_ML_PREDICTIONS,
        'auto_optimization': ENABLE_AUTO_OPTIMIZATION,
        'smc_analysis': ENABLE_SMC_ANALYSIS,
    }


def update_setting(key: str, value):
    """
    Обновить конкретную настройку
    
    Пример:
        update_setting('base_min_score', 70)
    """
    globals()[key.upper()] = value


# ============================================================================
# ВАЛИДАЦИЯ КОНФИГУРАЦИИ
# ============================================================================

def validate_config():
    """Проверка корректности конфигурации"""
    issues = []
    
    if not 40 <= BASE_MIN_SCORE <= 90:
        issues.append("BASE_MIN_SCORE должен быть между 40 и 90")
    
    if not 0.01 <= RISK_PER_TRADE <= 0.1:
        issues.append("RISK_PER_TRADE должен быть между 1% и 10%")
    
    if ACCOUNT_SIZE_USDT <= 0:
        issues.append("ACCOUNT_SIZE_USDT должен быть положительным")
    
    if not 0.3 <= MIN_CONFIDENCE_FOR_ENTRY <= 1.0:
        issues.append("MIN_CONFIDENCE_FOR_ENTRY должен быть между 0.3 и 1.0")
    
    if MAX_CONCURRENT_API_REQUESTS < 1:
        issues.append("MAX_CONCURRENT_API_REQUESTS должен быть >= 1")
    
    if STRICTNESS_LEVEL not in ['low', 'medium', 'high']:
        issues.append("STRICTNESS_LEVEL должен быть 'low', 'medium' или 'high'")
    
    if issues:
        print("⚠️ Проблемы с конфигурацией:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    
    print("✅ Конфигурация валидна")
    return True


# Автоматическая валидация при импорте
if __name__ == "__main__":
    validate_config()
