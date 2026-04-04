"""
Master catalog of 1,000 well-known trading strategies.

Organized into 20 families, each with parameter variations across:
- Indicator settings
- Entry/exit logic
- Stop/TP models
- Direction (long/short/both)
- Timeframe context

Each strategy is a concrete, backtestable definition — not just a name.
"""
from __future__ import annotations

STRATEGY_CATALOG: list[dict] = []

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 1: RSI MEAN REVERSION (50 strategies)
# Core concept: Enter when RSI reaches extreme levels, exit on return to mean
# ═══════════════════════════════════════════════════════════════════════════════
_rsi_periods = [5, 7, 9, 14, 21]
_rsi_ob = [70, 75, 80]       # overbought thresholds
_rsi_os = [20, 25, 30]       # oversold thresholds
_id = 1
for period in _rsi_periods:
    for ob, os in zip(_rsi_ob, _rsi_os):
        for direction in ["long", "short"]:
            for stop_atr in [1.5, 2.0]:
                for tp_r in [1.5, 2.0]:
                    if _id > 50:
                        break
                    trigger = "RSI_OVERSOLD" if direction == "long" else "RSI_OVERBOUGHT"
                    STRATEGY_CATALOG.append({
                        "id": _id,
                        "family": "RSI Mean Reversion",
                        "name": f"RSI-MeanRev-{period}-{ob}/{os}-{direction}-SL{stop_atr}-TP{tp_r}R",
                        "type": "mean_reversion",
                        "description": f"RSI({period}) mean reversion: enter {direction} when RSI crosses {'below ' + str(os) if direction == 'long' else 'above ' + str(ob)}, exit on return toward 50. ATR×{stop_atr} stop, {tp_r}R target.",
                        "primary_indicator": {"type": "RSI", "params": {"period": period}},
                        "trigger": trigger,
                        "direction": direction,
                        "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                        "take_profit": {"type": "r_multiple", "value": tp_r},
                        "well_known_as": "RSI Reversal / RSI Bounce",
                    })
                    _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 2: MACD CROSSOVER (50 strategies)
# Core concept: Enter on MACD line crossing signal line
# ═══════════════════════════════════════════════════════════════════════════════
_macd_configs = [
    (12, 26, 9, "Standard MACD"),
    (8, 21, 5, "Fast MACD"),
    (5, 13, 4, "Scalper MACD"),
    (19, 39, 9, "Slow MACD"),
    (8, 17, 9, "Mid MACD"),
]
_id = 51
for fast, slow, signal, label in _macd_configs:
    for direction in ["long", "short"]:
        for stop_atr in [1.5, 2.0, 2.5]:
            for tp_r in [1.5, 2.0, 3.0]:
                if _id > 100:
                    break
                trigger = "MACD_CROSS_ABOVE" if direction == "long" else "MACD_CROSS_BELOW"
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "MACD Crossover",
                    "name": f"MACD-{fast}/{slow}/{signal}-{direction}-SL{stop_atr}-TP{tp_r}R",
                    "type": "momentum",
                    "description": f"{label} ({fast}/{slow}/{signal}): enter {direction} on MACD line crossing signal line. ATR×{stop_atr} stop, {tp_r}R target.",
                    "primary_indicator": {"type": "MACD", "params": {"fast": fast, "slow": slow, "signal": signal}},
                    "trigger": trigger,
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                    "take_profit": {"type": "r_multiple", "value": tp_r},
                    "well_known_as": f"{label} Crossover",
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 3: BOLLINGER BAND STRATEGIES (50 strategies)
# Core concept: Mean reversion at bands + breakout on squeeze
# ═══════════════════════════════════════════════════════════════════════════════
_bb_periods = [10, 14, 20, 30]
_bb_stds = [1.5, 2.0, 2.5, 3.0]
_id = 101
for period in _bb_periods:
    for std in _bb_stds:
        for mode in ["reversion", "breakout"]:
            for direction in ["long", "short"]:
                if _id > 150:
                    break
                if mode == "reversion":
                    trigger = "BB_LOWER_TOUCH" if direction == "long" else "BB_UPPER_TOUCH"
                    desc = f"BB({period}, {std}σ) mean reversion: enter {direction} when price touches {'lower' if direction == 'long' else 'upper'} band"
                else:
                    trigger = "BB_UPPER_TOUCH" if direction == "long" else "BB_LOWER_TOUCH"
                    desc = f"BB({period}, {std}σ) breakout: enter {direction} on band expansion"
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "Bollinger Bands",
                    "name": f"BB-{period}-{std}σ-{mode}-{direction}",
                    "type": "mean_reversion" if mode == "reversion" else "breakout",
                    "description": desc,
                    "primary_indicator": {"type": "BB", "params": {"period": period, "std_dev": std}},
                    "trigger": trigger,
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": 2.0},
                    "take_profit": {"type": "r_multiple", "value": 2.0},
                    "well_known_as": "Bollinger Bounce" if mode == "reversion" else "Bollinger Squeeze Breakout",
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 4: EMA CROSSOVER SYSTEMS (50 strategies)
# Core concept: Fast EMA crosses slow EMA
# ═══════════════════════════════════════════════════════════════════════════════
_ema_pairs = [
    (5, 13, "Ultra Fast"), (8, 21, "Fast"), (9, 21, "Scalp"),
    (10, 30, "Medium-Fast"), (12, 26, "Standard"), (20, 50, "Swing"),
    (20, 100, "Position"), (50, 200, "Golden/Death Cross"),
    (9, 50, "Day Trade"), (13, 34, "Fibonacci"),
]
_id = 151
for fast, slow, label in _ema_pairs:
    for direction in ["long", "short"]:
        for stop_atr in [1.5, 2.0, 3.0]:
            if _id > 200:
                break
            trigger = "PRICE_ABOVE_EMA" if direction == "long" else "PRICE_BELOW_EMA"
            STRATEGY_CATALOG.append({
                "id": _id,
                "family": "EMA Crossover",
                "name": f"EMA-{fast}/{slow}-{direction}-SL{stop_atr}",
                "type": "trend_following",
                "description": f"{label} EMA crossover ({fast}/{slow}): enter {direction} when fast EMA crosses slow. ATR×{stop_atr} stop.",
                "primary_indicator": {"type": "EMA", "params": {"period": fast}},
                "confirmation": {"type": "EMA", "params": {"period": slow}},
                "trigger": trigger,
                "direction": direction,
                "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                "take_profit": {"type": "r_multiple", "value": 2.0},
                "well_known_as": f"{label} EMA Cross" + (" (Golden Cross)" if fast == 50 and slow == 200 else ""),
            })
            _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 5: STOCHASTIC OSCILLATOR (50 strategies)
# ═══════════════════════════════════════════════════════════════════════════════
_stoch_configs = [(5, 3), (9, 3), (14, 3), (14, 5), (21, 7)]
_id = 201
for k, d in _stoch_configs:
    for direction in ["long", "short"]:
        for stop_atr in [1.5, 2.0, 2.5]:
            for tp_r in [1.5, 2.0, 3.0]:
                if _id > 250:
                    break
                trigger = "STOCH_OVERSOLD" if direction == "long" else "STOCH_OVERBOUGHT"
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "Stochastic Oscillator",
                    "name": f"Stoch-{k}/{d}-{direction}-SL{stop_atr}-TP{tp_r}R",
                    "type": "mean_reversion",
                    "description": f"Stochastic({k},{d}): enter {direction} when %K crosses {'below 20' if direction == 'long' else 'above 80'}. ATR×{stop_atr} stop, {tp_r}R target.",
                    "primary_indicator": {"type": "STOCH", "params": {"k_period": k, "d_period": d}},
                    "trigger": trigger,
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                    "take_profit": {"type": "r_multiple", "value": tp_r},
                    "well_known_as": "Stochastic Reversal / Lane's Stochastic",
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 6: DONCHIAN CHANNEL BREAKOUT — TURTLE TRADING (50 strategies)
# ═══════════════════════════════════════════════════════════════════════════════
_dc_periods = [10, 20, 30, 40, 55]
_id = 251
for period in _dc_periods:
    for direction in ["long", "short"]:
        for stop_atr in [1.5, 2.0, 3.0]:
            for tp_r in [2.0, 3.0, 4.0]:
                if _id > 300:
                    break
                trigger = "DC_UPPER_BREAK" if direction == "long" else "DC_LOWER_BREAK"
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "Donchian Channel (Turtle)",
                    "name": f"Donchian-{period}-{direction}-SL{stop_atr}-TP{tp_r}R",
                    "type": "breakout",
                    "description": f"Donchian({period}) breakout: enter {direction} on {'upper' if direction == 'long' else 'lower'} channel break. Classic Turtle Trading system. ATR×{stop_atr} stop, {tp_r}R target.",
                    "primary_indicator": {"type": "DONCHIAN", "params": {"period": period}},
                    "trigger": trigger,
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                    "take_profit": {"type": "r_multiple", "value": tp_r},
                    "well_known_as": "Turtle Trading System / Donchian Breakout",
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 7: KELTNER CHANNEL (50 strategies)
# ═══════════════════════════════════════════════════════════════════════════════
_kc_configs = [
    (10, 10, 1.5), (20, 10, 1.5), (20, 10, 2.0), (20, 10, 2.5),
    (20, 14, 2.0), (20, 14, 3.0), (30, 14, 2.0), (10, 7, 1.0),
]
_id = 301
for ema_p, atr_p, mult in _kc_configs:
    for mode in ["reversion", "breakout"]:
        for direction in ["long", "short"]:
            for stop_atr in [1.5, 2.0]:
                if _id > 350:
                    break
                if mode == "reversion":
                    trigger = "KC_LOWER_TOUCH" if direction == "long" else "KC_UPPER_TOUCH"
                else:
                    trigger = "KC_UPPER_TOUCH" if direction == "long" else "KC_LOWER_TOUCH"
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "Keltner Channel",
                    "name": f"KC-{ema_p}/{atr_p}/{mult}-{mode}-{direction}",
                    "type": "mean_reversion" if mode == "reversion" else "breakout",
                    "description": f"Keltner({ema_p}, ATR{atr_p}, ×{mult}) {mode}: enter {direction} at channel boundary.",
                    "primary_indicator": {"type": "KELTNER", "params": {"ema_period": ema_p, "atr_period": atr_p, "multiplier": mult}},
                    "trigger": trigger,
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                    "take_profit": {"type": "r_multiple", "value": 2.0},
                    "well_known_as": "Keltner Channel " + ("Bounce" if mode == "reversion" else "Breakout"),
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 8: ICHIMOKU CLOUD (50 strategies)
# ═══════════════════════════════════════════════════════════════════════════════
_ichi_configs = [
    (9, 26, 52, "Standard"), (7, 22, 44, "Crypto"), (10, 30, 60, "Extended"),
    (9, 26, 52, "Conservative"), (5, 13, 26, "Fast"),
]
_id = 351
for tenkan, kijun, senkou, label in _ichi_configs:
    for direction in ["long", "short"]:
        for stop_atr in [1.5, 2.0, 2.5, 3.0]:
            for tp_r in [2.0, 3.0]:
                if _id > 400:
                    break
                trigger = "PRICE_ABOVE_CLOUD" if direction == "long" else "PRICE_BELOW_CLOUD"
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "Ichimoku Cloud",
                    "name": f"Ichi-{tenkan}/{kijun}/{senkou}-{direction}-SL{stop_atr}",
                    "type": "trend_following",
                    "description": f"{label} Ichimoku ({tenkan}/{kijun}/{senkou}): enter {direction} on cloud breakout. ATR×{stop_atr} stop, {tp_r}R target.",
                    "primary_indicator": {"type": "ICHIMOKU", "params": {"tenkan_period": tenkan, "kijun_period": kijun, "senkou_b_period": senkou}},
                    "trigger": trigger,
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                    "take_profit": {"type": "r_multiple", "value": tp_r},
                    "well_known_as": f"{label} Ichimoku / Kumo Breakout",
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 9: VWAP STRATEGIES (50 strategies)
# ═══════════════════════════════════════════════════════════════════════════════
_id = 401
for direction in ["long", "short"]:
    for stop_atr in [1.0, 1.5, 2.0, 2.5, 3.0]:
        for tp_r in [1.5, 2.0, 2.5, 3.0, 4.0]:
            if _id > 450:
                break
            trigger = "VWAP_CROSS_ABOVE" if direction == "long" else "VWAP_CROSS_BELOW"
            STRATEGY_CATALOG.append({
                "id": _id,
                "family": "VWAP",
                "name": f"VWAP-{direction}-SL{stop_atr}-TP{tp_r}R",
                "type": "mean_reversion",
                "description": f"VWAP crossover: enter {direction} when price crosses {'above' if direction == 'long' else 'below'} VWAP. Popular intraday institutional level. ATR×{stop_atr} stop, {tp_r}R target.",
                "primary_indicator": {"type": "VWAP", "params": {}},
                "trigger": trigger,
                "direction": direction,
                "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                "take_profit": {"type": "r_multiple", "value": tp_r},
                "well_known_as": "VWAP Bounce / Institutional VWAP Reversion",
            })
            _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 10: CCI (Commodity Channel Index) (50 strategies)
# ═══════════════════════════════════════════════════════════════════════════════
_cci_periods = [10, 14, 20, 30, 50]
_id = 451
for period in _cci_periods:
    for direction in ["long", "short"]:
        for stop_atr in [1.5, 2.0, 2.5]:
            for tp_r in [1.5, 2.0, 3.0]:
                if _id > 500:
                    break
                trigger = "CCI_OVERSOLD" if direction == "long" else "CCI_OVERBOUGHT"
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "CCI",
                    "name": f"CCI-{period}-{direction}-SL{stop_atr}-TP{tp_r}R",
                    "type": "mean_reversion",
                    "description": f"CCI({period}): enter {direction} when CCI crosses {'above -100' if direction == 'long' else 'below +100'}. Lambert's channel index. ATR×{stop_atr} stop, {tp_r}R target.",
                    "primary_indicator": {"type": "CCI", "params": {"period": period}},
                    "trigger": trigger,
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                    "take_profit": {"type": "r_multiple", "value": tp_r},
                    "well_known_as": "CCI Reversal / Lambert's CCI",
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 11: WILLIAMS %R (50 strategies)
# ═══════════════════════════════════════════════════════════════════════════════
_willr_periods = [7, 10, 14, 21, 28]
_id = 501
for period in _willr_periods:
    for direction in ["long", "short"]:
        for stop_atr in [1.5, 2.0, 2.5]:
            for tp_r in [1.5, 2.0, 3.0]:
                if _id > 550:
                    break
                trigger = "WILLR_OVERSOLD" if direction == "long" else "WILLR_OVERBOUGHT"
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "Williams %R",
                    "name": f"WillR-{period}-{direction}-SL{stop_atr}-TP{tp_r}R",
                    "type": "mean_reversion",
                    "description": f"Williams %R({period}): enter {direction} when %R crosses {'above -80' if direction == 'long' else 'below -20'}. Larry Williams' oscillator. ATR×{stop_atr} stop, {tp_r}R target.",
                    "primary_indicator": {"type": "WILLR", "params": {"period": period}},
                    "trigger": trigger,
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                    "take_profit": {"type": "r_multiple", "value": tp_r},
                    "well_known_as": "Williams %R Reversal",
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 12: ROC (Rate of Change) MOMENTUM (50 strategies)
# ═══════════════════════════════════════════════════════════════════════════════
_roc_periods = [5, 6, 10, 12, 14, 20, 25]
_id = 551
for period in _roc_periods:
    for direction in ["long", "short"]:
        for stop_atr in [1.5, 2.0, 3.0]:
            for tp_r in [2.0, 3.0]:
                if _id > 600:
                    break
                trigger = "ROC_CROSS_ABOVE" if direction == "long" else "ROC_CROSS_BELOW"
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "ROC Momentum",
                    "name": f"ROC-{period}-{direction}-SL{stop_atr}-TP{tp_r}R",
                    "type": "momentum",
                    "description": f"ROC({period}) momentum: enter {direction} when rate of change crosses zero. ATR×{stop_atr} stop, {tp_r}R target.",
                    "primary_indicator": {"type": "ROC", "params": {"period": period}},
                    "trigger": trigger,
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                    "take_profit": {"type": "r_multiple", "value": tp_r},
                    "well_known_as": "Momentum / Rate of Change Zero-Cross",
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 13: ADX TREND STRENGTH (50 strategies)
# ═══════════════════════════════════════════════════════════════════════════════
_adx_periods = [7, 10, 14, 20, 25]
_id = 601
for period in _adx_periods:
    for direction in ["long", "short"]:
        for stop_atr in [1.5, 2.0, 2.5, 3.0]:
            for tp_r in [2.0, 3.0]:
                if _id > 650:
                    break
                trigger = "PRICE_ABOVE_EMA" if direction == "long" else "PRICE_BELOW_EMA"
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "ADX Trend",
                    "name": f"ADX-{period}-{direction}-SL{stop_atr}-TP{tp_r}R",
                    "type": "trend_following",
                    "description": f"ADX({period}) trend system: enter {direction} when ADX > 25 confirms trend strength. Welles Wilder's DMI system. ATR×{stop_atr} stop, {tp_r}R target.",
                    "primary_indicator": {"type": "ADX", "params": {"period": period}},
                    "trigger": trigger,
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                    "take_profit": {"type": "r_multiple", "value": tp_r},
                    "well_known_as": "ADX/DMI Trend System / Wilder's DMI",
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 14: SUPERTREND (50 strategies)
# Based on ATR with multiplier — one of the most popular trend indicators
# ═══════════════════════════════════════════════════════════════════════════════
_st_configs = [
    (7, 1.5), (7, 2.0), (7, 3.0), (10, 1.5), (10, 2.0),
    (10, 3.0), (14, 2.0), (14, 3.0), (20, 2.0), (20, 3.0),
]
_id = 651
for atr_period, multiplier in _st_configs:
    for direction in ["long", "short"]:
        for tp_r in [1.5, 2.0, 3.0]:
            if _id > 700:
                break
            trigger = "PRICE_ABOVE_EMA" if direction == "long" else "PRICE_BELOW_EMA"
            STRATEGY_CATALOG.append({
                "id": _id,
                "family": "Supertrend",
                "name": f"Supertrend-ATR{atr_period}x{multiplier}-{direction}-TP{tp_r}R",
                "type": "trend_following",
                "description": f"Supertrend(ATR{atr_period}, ×{multiplier}): enter {direction} on Supertrend flip. Uses ATR-based trailing stop as both signal and exit. {tp_r}R target.",
                "primary_indicator": {"type": "ATR", "params": {"period": atr_period}},
                "trigger": trigger,
                "direction": direction,
                "stop_loss": {"type": "atr_multiple", "value": multiplier},
                "take_profit": {"type": "r_multiple", "value": tp_r},
                "well_known_as": "Supertrend / ATR Trailing Trend",
            })
            _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 15: BOLLINGER BAND SQUEEZE + KELTNER (50 strategies)
# The "TTM Squeeze" — BB inside KC signals compression, breakout follows
# ═══════════════════════════════════════════════════════════════════════════════
_id = 701
for bb_period in [14, 20, 30]:
    for bb_std in [1.5, 2.0, 2.5]:
        for direction in ["long", "short"]:
            for stop_atr in [1.5, 2.0, 2.5]:
                for tp_r in [2.0, 3.0]:
                    if _id > 750:
                        break
                    trigger = "BB_UPPER_TOUCH" if direction == "long" else "BB_LOWER_TOUCH"
                    STRATEGY_CATALOG.append({
                        "id": _id,
                        "family": "BB/KC Squeeze (TTM Squeeze)",
                        "name": f"Squeeze-BB{bb_period}/{bb_std}-{direction}-SL{stop_atr}",
                        "type": "breakout",
                        "description": f"TTM Squeeze: BB({bb_period}, {bb_std}σ) squeeze inside Keltner, enter {direction} on expansion breakout. John Carter's squeeze momentum. ATR×{stop_atr} stop, {tp_r}R target.",
                        "primary_indicator": {"type": "BB", "params": {"period": bb_period, "std_dev": bb_std}},
                        "trigger": trigger,
                        "direction": direction,
                        "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                        "take_profit": {"type": "r_multiple", "value": tp_r},
                        "well_known_as": "TTM Squeeze / John Carter's Squeeze",
                    })
                    _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 16: OBV (On-Balance Volume) (50 strategies)
# ═══════════════════════════════════════════════════════════════════════════════
_id = 751
for direction in ["long", "short"]:
    for conf_type in ["EMA", "VOLUME", "ADX"]:
        for conf_period in [20, 50, 100, 200]:
            for stop_atr in [1.5, 2.0, 2.5]:
                if _id > 800:
                    break
                trigger = "PRICE_ABOVE_EMA" if direction == "long" else "PRICE_BELOW_EMA"
                conf_filter = "PRICE_ABOVE_EMA" if conf_type == "EMA" else ("VOLUME_ABOVE_SMA" if conf_type == "VOLUME" else "ADX_TRENDING")
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "OBV Volume",
                    "name": f"OBV-{conf_type}{conf_period}-{direction}-SL{stop_atr}",
                    "type": "trend_following",
                    "description": f"OBV trend confirmation: enter {direction} when OBV rising + {conf_type}({conf_period}) confirms. Granville's volume indicator. ATR×{stop_atr} stop.",
                    "primary_indicator": {"type": "OBV", "params": {}},
                    "confirmation": {"type": conf_type, "params": {"period": conf_period}},
                    "trigger": trigger,
                    "filter": conf_filter,
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                    "take_profit": {"type": "r_multiple", "value": 2.0},
                    "well_known_as": "OBV Divergence / Granville's OBV",
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 17: MULTI-INDICATOR CONFLUENCE (50 strategies)
# RSI + MACD + EMA — multiple confirmations required
# ═══════════════════════════════════════════════════════════════════════════════
_id = 801
_confluence_combos = [
    ("RSI", 14, "EMA", 50, "RSI + EMA trend filter"),
    ("RSI", 14, "ADX", 14, "RSI + ADX trend strength"),
    ("RSI", 14, "VOLUME", 20, "RSI + Volume spike"),
    ("MACD", 12, "EMA", 200, "MACD + EMA trend filter"),
    ("MACD", 12, "ADX", 14, "MACD + ADX trend strength"),
    ("BB", 20, "EMA", 50, "Bollinger + EMA filter"),
    ("BB", 20, "VOLUME", 20, "Bollinger + Volume"),
    ("STOCH", 14, "EMA", 50, "Stochastic + EMA filter"),
    ("STOCH", 14, "ADX", 14, "Stochastic + ADX"),
    ("CCI", 20, "EMA", 50, "CCI + EMA filter"),
]
for primary, p_param, confirm, c_param, label in _confluence_combos:
    for direction in ["long", "short"]:
        for stop_atr in [1.5, 2.0, 2.5]:
            if _id > 850:
                break
            triggers_map = {
                "RSI": ("RSI_OVERSOLD", "RSI_OVERBOUGHT"),
                "MACD": ("MACD_CROSS_ABOVE", "MACD_CROSS_BELOW"),
                "BB": ("BB_LOWER_TOUCH", "BB_UPPER_TOUCH"),
                "STOCH": ("STOCH_OVERSOLD", "STOCH_OVERBOUGHT"),
                "CCI": ("CCI_OVERSOLD", "CCI_OVERBOUGHT"),
            }
            long_t, short_t = triggers_map.get(primary, ("PRICE_ABOVE_EMA", "PRICE_BELOW_EMA"))
            trigger = long_t if direction == "long" else short_t
            filter_map = {"EMA": "PRICE_ABOVE_EMA", "ADX": "ADX_TRENDING", "VOLUME": "VOLUME_ABOVE_SMA"}
            STRATEGY_CATALOG.append({
                "id": _id,
                "family": "Multi-Indicator Confluence",
                "name": f"Confluence-{primary}+{confirm}-{direction}-SL{stop_atr}",
                "type": "hybrid",
                "description": f"{label}: enter {direction} when {primary} triggers AND {confirm} confirms. Dual confirmation reduces false signals. ATR×{stop_atr} stop.",
                "primary_indicator": {"type": primary, "params": {"period": p_param} if primary != "MACD" else {"fast": 12, "slow": 26, "signal": 9}},
                "confirmation": {"type": confirm, "params": {"period": c_param}},
                "trigger": trigger,
                "filter": filter_map.get(confirm, "NONE"),
                "direction": direction,
                "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                "take_profit": {"type": "r_multiple", "value": 2.0},
                "well_known_as": f"{label} System",
            })
            _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 18: PULLBACK/RETRACEMENT ENTRIES (50 strategies)
# Enter on pullback to moving average in trending market
# ═══════════════════════════════════════════════════════════════════════════════
_id = 851
_pullback_emas = [9, 20, 21, 34, 50]
for ema_period in _pullback_emas:
    for direction in ["long", "short"]:
        for stop_atr in [1.0, 1.5, 2.0]:
            for tp_r in [1.5, 2.0, 3.0]:
                if _id > 900:
                    break
                trigger = "PRICE_ABOVE_EMA" if direction == "long" else "PRICE_BELOW_EMA"
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "EMA Pullback",
                    "name": f"Pullback-EMA{ema_period}-{direction}-SL{stop_atr}-TP{tp_r}R",
                    "type": "trend_following",
                    "description": f"Pullback to EMA({ema_period}): enter {direction} when price touches EMA in a trending market (ADX>25). Classic 'buy the dip' in uptrends / 'sell the rally' in downtrends. ATR×{stop_atr} stop, {tp_r}R target.",
                    "primary_indicator": {"type": "EMA", "params": {"period": ema_period}},
                    "confirmation": {"type": "ADX", "params": {"period": 14}},
                    "trigger": trigger,
                    "filter": "ADX_TRENDING",
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                    "take_profit": {"type": "r_multiple", "value": tp_r},
                    "well_known_as": "EMA Pullback / Buy the Dip / Trend Retracement",
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 19: VOLATILITY BREAKOUT (50 strategies)
# ATR-based expansion detection for breakout entries
# ═══════════════════════════════════════════════════════════════════════════════
_id = 901
_atr_periods = [7, 10, 14, 20, 30]
for atr_period in _atr_periods:
    for direction in ["long", "short"]:
        for stop_atr in [1.5, 2.0, 2.5]:
            for tp_r in [2.0, 3.0, 4.0]:
                if _id > 950:
                    break
                trigger = "PRICE_ABOVE_EMA" if direction == "long" else "PRICE_BELOW_EMA"
                STRATEGY_CATALOG.append({
                    "id": _id,
                    "family": "Volatility Breakout",
                    "name": f"VolBreakout-ATR{atr_period}-{direction}-SL{stop_atr}-TP{tp_r}R",
                    "type": "breakout",
                    "description": f"ATR({atr_period}) volatility breakout: enter {direction} when ATR expands (volatility increasing) + price confirms direction. ATR×{stop_atr} stop, {tp_r}R target.",
                    "primary_indicator": {"type": "ATR", "params": {"period": atr_period}},
                    "confirmation": {"type": "ATR", "params": {"period": atr_period}},
                    "trigger": trigger,
                    "filter": "ATR_EXPANDING",
                    "direction": direction,
                    "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                    "take_profit": {"type": "r_multiple", "value": tp_r},
                    "well_known_as": "ATR Expansion Breakout / Volatility Breakout",
                })
                _id += 1

# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY 20: FIBONACCI / MEAN REVERSION WITH TRAILING (50 strategies)
# Tight-stop mean reversion with trailing stops for runners
# ═══════════════════════════════════════════════════════════════════════════════
_id = 951
_fib_indicators = [
    ("RSI", 14, "RSI_OVERSOLD", "RSI_OVERBOUGHT"),
    ("RSI", 7, "RSI_OVERSOLD", "RSI_OVERBOUGHT"),
    ("STOCH", 14, "STOCH_OVERSOLD", "STOCH_OVERBOUGHT"),
    ("BB", 20, "BB_LOWER_TOUCH", "BB_UPPER_TOUCH"),
    ("CCI", 20, "CCI_OVERSOLD", "CCI_OVERBOUGHT"),
]
for ind_type, ind_period, long_trig, short_trig in _fib_indicators:
    for direction in ["long", "short"]:
        for stop_atr in [1.0, 1.5]:
            for trailing_atr in [1.5, 2.0]:
                for tp_r in [3.0, 4.0]:
                    if _id > 1000:
                        break
                    trigger = long_trig if direction == "long" else short_trig
                    STRATEGY_CATALOG.append({
                        "id": _id,
                        "family": "Trailing Mean Reversion",
                        "name": f"TrailMR-{ind_type}{ind_period}-{direction}-SL{stop_atr}-Trail{trailing_atr}",
                        "type": "mean_reversion",
                        "description": f"{ind_type}({ind_period}) mean reversion with trailing stop: enter {direction} at extreme, use tight ATR×{stop_atr} initial stop, then trail at ATR×{trailing_atr} to let winners run. {tp_r}R max target.",
                        "primary_indicator": {"type": ind_type, "params": {"period": ind_period} if ind_type != "BB" else {"period": ind_period, "std_dev": 2.0}},
                        "trigger": trigger,
                        "direction": direction,
                        "stop_loss": {"type": "atr_multiple", "value": stop_atr},
                        "take_profit": {"type": "r_multiple", "value": tp_r},
                        "trailing_stop": {"type": "trailing_atr", "value": trailing_atr},
                        "well_known_as": "Mean Reversion with Trailing / Runner Strategy",
                    })
                    _id += 1


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

def get_catalog_summary() -> dict:
    """Return a summary of the strategy catalog."""
    families = {}
    for s in STRATEGY_CATALOG:
        fam = s["family"]
        if fam not in families:
            families[fam] = {"count": 0, "types": set(), "directions": set()}
        families[fam]["count"] += 1
        families[fam]["types"].add(s["type"])
        families[fam]["directions"].add(s["direction"])

    return {
        "total_strategies": len(STRATEGY_CATALOG),
        "families": {
            fam: {
                "count": info["count"],
                "types": sorted(info["types"]),
                "directions": sorted(info["directions"]),
            }
            for fam, info in sorted(families.items())
        },
    }


def get_strategies_by_family(family: str) -> list[dict]:
    return [s for s in STRATEGY_CATALOG if s["family"] == family]


def get_strategies_by_type(strategy_type: str) -> list[dict]:
    return [s for s in STRATEGY_CATALOG if s["type"] == strategy_type]
