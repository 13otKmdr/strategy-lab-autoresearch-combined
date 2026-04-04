"""
Pine Script v5 converter -- translates StrategyDefinition and ORB configs
into copy-pasteable TradingView Pine Script.

Public API:
    convert_to_pine(strategy)          -> str   (standard strategies)
    convert_orb_to_pine(orb_config)    -> str   (ORB breakout strategies)
    get_pine_indicator(ind_type, params) -> str  (single indicator snippet)
    get_pine_condition(trigger, ind_type) -> str (single boolean expression)
"""
from __future__ import annotations

from app.models.strategy import StrategyDefinition


# ---------------------------------------------------------------------------
# Indicator code generators
# ---------------------------------------------------------------------------

_INDICATOR_GENERATORS: dict[str, callable] = {}


def _reg(name: str):
    """Decorator to register an indicator generator."""
    def wrapper(fn):
        _INDICATOR_GENERATORS[name] = fn
        return fn
    return wrapper


@_reg("RSI")
def _pine_rsi(params: dict, prefix: str = "") -> str:
    period = params.get("period", 14)
    var = f"{prefix}rsiValue"
    return f"{var} = ta.rsi(close, {period})"


@_reg("EMA")
def _pine_ema(params: dict, prefix: str = "") -> str:
    period = params.get("period", 20)
    var = f"{prefix}emaValue"
    return f"{var} = ta.ema(close, {period})"


@_reg("SMA")
def _pine_sma(params: dict, prefix: str = "") -> str:
    period = params.get("period", 20)
    var = f"{prefix}smaValue"
    return f"{var} = ta.sma(close, {period})"


@_reg("MACD")
def _pine_macd(params: dict, prefix: str = "") -> str:
    fast = params.get("fast", 12)
    slow = params.get("slow", 26)
    signal = params.get("signal", 9)
    p = prefix
    lines = [
        f"[{p}macdLine, {p}macdSig, {p}macdHist] = ta.macd(close, {fast}, {slow}, {signal})",
    ]
    return "\n".join(lines)


@_reg("BB")
def _pine_bb(params: dict, prefix: str = "") -> str:
    period = params.get("period", 20)
    std_dev = params.get("std_dev", 2.0)
    p = prefix
    lines = [
        f"[{p}bbMiddle, {p}bbUpper, {p}bbLower] = ta.bb(close, {period}, {std_dev})",
    ]
    return "\n".join(lines)


@_reg("BOLLINGER")
def _pine_bollinger(params: dict, prefix: str = "") -> str:
    return _pine_bb(params, prefix)


@_reg("STOCH")
def _pine_stoch(params: dict, prefix: str = "") -> str:
    k_period = params.get("k_period", 14)
    d_period = params.get("d_period", 3)
    smooth_k = params.get("smooth_k", 1)
    p = prefix
    lines = [
        f"{p}stochK = ta.stoch(close, high, low, {k_period})",
        f"{p}stochD = ta.sma({p}stochK, {d_period})",
    ]
    return "\n".join(lines)


@_reg("ATR")
def _pine_atr(params: dict, prefix: str = "") -> str:
    period = params.get("period", 14)
    var = f"{prefix}atrValue"
    return f"{var} = ta.atr({period})"


@_reg("ADX")
def _pine_adx(params: dict, prefix: str = "") -> str:
    period = params.get("period", 14)
    p = prefix
    lines = [
        f"[{p}adxDiPlus, {p}adxDiMinus, {p}adxValue] = ta.dmi({period}, {period})",
    ]
    return "\n".join(lines)


@_reg("CCI")
def _pine_cci(params: dict, prefix: str = "") -> str:
    period = params.get("period", 20)
    var = f"{prefix}cciValue"
    return f"{var} = ta.cci(close, {period})"


@_reg("WILLR")
def _pine_willr(params: dict, prefix: str = "") -> str:
    period = params.get("period", 14)
    p = prefix
    # Pine Script doesn't have a built-in Williams %R -- compute manually
    lines = [
        f"{p}willrHH = ta.highest(high, {period})",
        f"{p}willrLL = ta.lowest(low, {period})",
        f"{p}willrValue = ({p}willrHH - close) / ({p}willrHH - {p}willrLL) * -100",
    ]
    return "\n".join(lines)


@_reg("ROC")
def _pine_roc(params: dict, prefix: str = "") -> str:
    period = params.get("period", 12)
    var = f"{prefix}rocValue"
    return f"{var} = ta.roc(close, {period})"


@_reg("DONCHIAN")
def _pine_donchian(params: dict, prefix: str = "") -> str:
    period = params.get("period", 20)
    p = prefix
    lines = [
        f"{p}dcUpper = ta.highest(high, {period})",
        f"{p}dcLower = ta.lowest(low, {period})",
        f"{p}dcMiddle = ({p}dcUpper + {p}dcLower) / 2",
    ]
    return "\n".join(lines)


@_reg("KELTNER")
def _pine_keltner(params: dict, prefix: str = "") -> str:
    ema_period = params.get("ema_period", 20)
    atr_period = params.get("atr_period", 10)
    multiplier = params.get("multiplier", 2.0)
    p = prefix
    lines = [
        f"{p}kcMiddle = ta.ema(close, {ema_period})",
        f"{p}kcAtr = ta.atr({atr_period})",
        f"{p}kcUpper = {p}kcMiddle + {multiplier} * {p}kcAtr",
        f"{p}kcLower = {p}kcMiddle - {multiplier} * {p}kcAtr",
    ]
    return "\n".join(lines)


@_reg("ICHIMOKU")
def _pine_ichimoku(params: dict, prefix: str = "") -> str:
    tenkan = params.get("tenkan_period", 9)
    kijun = params.get("kijun_period", 26)
    senkou_b = params.get("senkou_b_period", 52)
    p = prefix
    lines = [
        f"{p}tenkan = (ta.highest(high, {tenkan}) + ta.lowest(low, {tenkan})) / 2",
        f"{p}kijun  = (ta.highest(high, {kijun}) + ta.lowest(low, {kijun})) / 2",
        f"{p}senkouA = ({p}tenkan + {p}kijun) / 2",
        f"{p}senkouB = (ta.highest(high, {senkou_b}) + ta.lowest(low, {senkou_b})) / 2",
        f"{p}cloudUpper = math.max({p}senkouA, {p}senkouB)",
        f"{p}cloudLower = math.min({p}senkouA, {p}senkouB)",
    ]
    return "\n".join(lines)


@_reg("VWAP")
def _pine_vwap(params: dict, prefix: str = "") -> str:
    var = f"{prefix}vwapValue"
    return f"{var} = ta.vwap(hlc3)"


@_reg("OBV")
def _pine_obv(params: dict, prefix: str = "") -> str:
    var = f"{prefix}obvValue"
    return f"{var} = ta.obv()"


@_reg("VOLUME")
def _pine_volume(params: dict, prefix: str = "") -> str:
    period = params.get("period", 20)
    var = f"{prefix}volSma"
    return f"{var} = ta.sma(volume, {period})"


# ---------------------------------------------------------------------------
# Condition code generators  (entry triggers -> Pine boolean expressions)
# ---------------------------------------------------------------------------

_CONDITION_MAP: dict[str, str] = {
    # RSI
    "RSI_OVERSOLD":
        "ta.crossunder(rsiValue, 30)",
    "RSI_OVERBOUGHT":
        "ta.crossover(rsiValue, 70)",

    # EMA crossover
    "PRICE_ABOVE_EMA":
        "ta.crossover(close, emaValue)",
    "PRICE_BELOW_EMA":
        "ta.crossunder(close, emaValue)",

    # MACD
    "MACD_CROSS_ABOVE":
        "ta.crossover(macdLine, macdSig)",
    "MACD_CROSS_BELOW":
        "ta.crossunder(macdLine, macdSig)",

    # Bollinger Bands
    "BB_LOWER_TOUCH":
        "(close <= bbLower and close[1] > bbLower[1])",
    "BB_UPPER_TOUCH":
        "(close >= bbUpper and close[1] < bbUpper[1])",

    # Stochastic
    "STOCH_OVERSOLD":
        "ta.crossunder(stochK, 20)",
    "STOCH_OVERBOUGHT":
        "ta.crossover(stochK, 80)",

    # CCI
    "CCI_OVERSOLD":
        "ta.crossover(cciValue, -100)",
    "CCI_OVERBOUGHT":
        "ta.crossunder(cciValue, 100)",

    # Williams %R
    "WILLR_OVERSOLD":
        "ta.crossover(willrValue, -80)",
    "WILLR_OVERBOUGHT":
        "ta.crossunder(willrValue, -20)",

    # ROC
    "ROC_CROSS_ABOVE":
        "ta.crossover(rocValue, 0)",
    "ROC_CROSS_BELOW":
        "ta.crossunder(rocValue, 0)",

    # Donchian
    "DC_UPPER_BREAK":
        "(close > dcUpper[1])",
    "DC_LOWER_BREAK":
        "(close < dcLower[1])",

    # Keltner
    "KC_LOWER_TOUCH":
        "(close <= kcLower and close[1] > kcLower[1])",
    "KC_UPPER_TOUCH":
        "(close >= kcUpper and close[1] < kcUpper[1])",

    # Ichimoku
    "PRICE_ABOVE_CLOUD":
        "(close[1] <= cloudUpper[1] and close > cloudUpper)",
    "PRICE_BELOW_CLOUD":
        "(close[1] >= cloudLower[1] and close < cloudLower)",

    # VWAP
    "VWAP_CROSS_ABOVE":
        "ta.crossover(close, vwapValue)",
    "VWAP_CROSS_BELOW":
        "ta.crossunder(close, vwapValue)",
}

# Confirmation filters -> Pine boolean expressions
_CONFIRMATION_MAP: dict[str, str] = {
    "PRICE_ABOVE_EMA":  "close > confEma",
    "PRICE_BELOW_EMA":  "close < confEma",
    "VOLUME_ABOVE_SMA": "volume > confVolSma",
    "ATR_EXPANDING":    "atrValue > atrValue[1]",
    "ADX_TRENDING":     "confAdxValue > 25",
    "OBV_RISING":       "confObvValue > confObvValue[1]",
    "NONE":             "true",
}


# ---------------------------------------------------------------------------
# Short-trigger lookup (mirrors signals._SHORT_TRIGGERS)
# ---------------------------------------------------------------------------

_SHORT_TRIGGERS = frozenset({
    "RSI_OVERBOUGHT", "PRICE_BELOW_EMA", "MACD_CROSS_BELOW",
    "BB_UPPER_TOUCH", "STOCH_OVERBOUGHT", "CCI_OVERBOUGHT",
    "WILLR_OVERBOUGHT", "ROC_CROSS_BELOW", "DC_LOWER_BREAK",
    "KC_UPPER_TOUCH", "PRICE_BELOW_CLOUD", "VWAP_CROSS_BELOW",
})


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_pine_indicator(indicator_type: str, params: dict) -> str:
    """Return Pine Script code for computing a specific indicator.

    Parameters
    ----------
    indicator_type : str
        One of RSI, EMA, SMA, MACD, BB, BOLLINGER, STOCH, ATR, ADX, CCI,
        WILLR, ROC, DONCHIAN, KELTNER, ICHIMOKU, VWAP, OBV, VOLUME.
    params : dict
        Indicator parameters (period, fast, slow, etc.).

    Returns
    -------
    str
        One or more lines of Pine Script v5 code.
    """
    gen = _INDICATOR_GENERATORS.get(indicator_type.upper())
    if gen is None:
        return f"// Unknown indicator type: {indicator_type}"
    return gen(params)


def get_pine_condition(trigger: str, indicator_type: str) -> str:
    """Return the Pine Script boolean expression for an entry trigger.

    Parameters
    ----------
    trigger : str
        Entry trigger name (e.g. ``RSI_OVERSOLD``).
    indicator_type : str
        The primary indicator type (used for fallback messaging only).

    Returns
    -------
    str
        A Pine Script boolean expression string.
    """
    expr = _CONDITION_MAP.get(trigger.upper())
    if expr is None:
        return f"false  // unsupported trigger: {trigger}"
    return expr


# ---------------------------------------------------------------------------
# Indicator requirement map -- which indicator(s) each trigger needs
# ---------------------------------------------------------------------------

_TRIGGER_INDICATOR_REQ: dict[str, str] = {
    "RSI_OVERSOLD":      "RSI",
    "RSI_OVERBOUGHT":    "RSI",
    "PRICE_ABOVE_EMA":   "EMA",
    "PRICE_BELOW_EMA":   "EMA",
    "MACD_CROSS_ABOVE":  "MACD",
    "MACD_CROSS_BELOW":  "MACD",
    "BB_LOWER_TOUCH":    "BB",
    "BB_UPPER_TOUCH":    "BB",
    "STOCH_OVERSOLD":    "STOCH",
    "STOCH_OVERBOUGHT":  "STOCH",
    "CCI_OVERSOLD":      "CCI",
    "CCI_OVERBOUGHT":    "CCI",
    "WILLR_OVERSOLD":    "WILLR",
    "WILLR_OVERBOUGHT":  "WILLR",
    "ROC_CROSS_ABOVE":   "ROC",
    "ROC_CROSS_BELOW":   "ROC",
    "DC_UPPER_BREAK":    "DONCHIAN",
    "DC_LOWER_BREAK":    "DONCHIAN",
    "KC_LOWER_TOUCH":    "KELTNER",
    "KC_UPPER_TOUCH":    "KELTNER",
    "PRICE_ABOVE_CLOUD": "ICHIMOKU",
    "PRICE_BELOW_CLOUD": "ICHIMOKU",
    "VWAP_CROSS_ABOVE":  "VWAP",
    "VWAP_CROSS_BELOW":  "VWAP",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_confirmation_code(conf_type: str, conf_params: dict) -> tuple[str, str, str]:
    """Return (indicator_code, long_filter_expr, short_filter_expr) for a confirmation type."""
    ct = conf_type.upper()
    if ct in ("EMA", "SMA"):
        period = conf_params.get("period", 50)
        fn = "ta.ema" if ct == "EMA" else "ta.sma"
        ind_code = f"confEma = {fn}(close, {period})"
        return ind_code, "close > confEma", "close < confEma"
    if ct == "VOLUME":
        period = conf_params.get("period", 20)
        ind_code = f"confVolSma = ta.sma(volume, {period})"
        return ind_code, "volume > confVolSma", "volume > confVolSma"
    if ct == "ATR":
        period = conf_params.get("period", 14)
        # ATR already computed for stop/TP -- reuse atrValue
        return "", "atrValue > atrValue[1]", "atrValue > atrValue[1]"
    if ct == "ADX":
        period = conf_params.get("period", 14)
        ind_code = f"[confAdxDiPlus, confAdxDiMinus, confAdxValue] = ta.dmi({period}, {period})"
        return ind_code, "confAdxValue > 25", "confAdxValue > 25"
    if ct == "OBV":
        ind_code = "confObvValue = ta.obv()"
        return ind_code, "confObvValue > confObvValue[1]", "confObvValue > confObvValue[1]"
    # NONE or unknown
    return "", "true", "true"


def _confirmation_filter_expr(filter_name: str) -> tuple[str, str]:
    """Return (long_filter, short_filter) based on the filter name from entry rules."""
    fn = filter_name.upper() if filter_name else "NONE"
    if fn in ("PRICE_ABOVE_EMA", "PRICE_BELOW_EMA"):
        # When confirmation indicator is EMA, PRICE_ABOVE_EMA means:
        #   long -> close > confEma;  short -> close < confEma
        return "close > confEma", "close < confEma"
    expr = _CONFIRMATION_MAP.get(fn, "true")
    return expr, expr


def _strategy_direction(trigger: str) -> str:
    """Determine if strategy is long-only, short-only, or both based on trigger."""
    if trigger.upper() in _SHORT_TRIGGERS:
        return "short"
    return "long"


# ---------------------------------------------------------------------------
# Main converter: StrategyDefinition -> Pine Script v5
# ---------------------------------------------------------------------------

def convert_to_pine(strategy: StrategyDefinition) -> str:
    """Convert a StrategyDefinition into a complete Pine Script v5 strategy.

    The output is a valid TradingView Pine Script that can be pasted directly
    into the Pine Editor and compiled without errors.
    """
    name = strategy.strategy_name or strategy.strategy_id
    trigger = (strategy.entry.get("trigger") or strategy.entry_rules.get("trigger", "NONE")).upper()
    filter_name = (strategy.entry.get("filter") or strategy.entry_rules.get("filter", "NONE")).upper()

    # Primary indicator
    p_type = strategy.primary_indicator.get("type", "RSI").upper()
    p_params = strategy.primary_indicator.get("params", {})

    # Confirmation indicator
    c_type = strategy.confirmation_indicator.get("type", "EMA").upper() if strategy.confirmation_indicator else "NONE"
    c_params = strategy.confirmation_indicator.get("params", {}) if strategy.confirmation_indicator else {}

    # Stop loss / take profit from exit dict (preferred) or top-level fields
    sl_cfg = strategy.exit.get("stop_loss", strategy.stop_loss_logic) if strategy.exit else strategy.stop_loss_logic
    tp_cfg = strategy.exit.get("take_profit", strategy.take_profit_logic) if strategy.exit else strategy.take_profit_logic
    trailing_cfg = strategy.trailing_stop_or_break_even_logic or {}
    time_exit_bars = (strategy.exit.get("time_exit_bars") or strategy.exit_rules.get("time_exit_bars", 0)) if strategy.exit else 0

    sl_type = sl_cfg.get("type", "atr_multiple") if sl_cfg else "atr_multiple"
    sl_value = float(sl_cfg.get("value", 2.0)) if sl_cfg else 2.0
    tp_type = tp_cfg.get("type", "r_multiple") if tp_cfg else "r_multiple"
    tp_value = float(tp_cfg.get("value", 2.0)) if tp_cfg else 2.0

    trailing_type = trailing_cfg.get("type", "none")
    trailing_value = float(trailing_cfg.get("value", 1.5)) if trailing_cfg.get("value") else 1.5
    trailing_trigger_r = float(trailing_cfg.get("trigger_r", 1.0)) if trailing_cfg.get("trigger_r") else 1.0

    direction = _strategy_direction(trigger)

    # ── Assemble the script ─────────────────────────────────────────────
    lines: list[str] = []

    # Header
    lines.append("//@version=5")
    lines.append(f'strategy("StrategyLab: {name}", overlay=true, initial_capital=50000,')
    lines.append('         default_qty_type=strategy.percent_of_equity, default_qty_value=0.25,')
    lines.append('         commission_type=strategy.commission.percent, commission_value=0.05)')
    lines.append("")

    # ── Primary indicator ───────────────────────────────────────────────
    lines.append("// ── Primary Indicator ──")
    # Get indicator code from the trigger's requirement or the primary_indicator type
    required_ind = _TRIGGER_INDICATOR_REQ.get(trigger, p_type)
    # Use the primary_indicator params for generation
    ind_params = p_params
    # For EMA/SMA triggers using an EMA primary, we use emaValue for the trigger
    primary_code = get_pine_indicator(required_ind, ind_params)
    lines.append(primary_code)
    lines.append("")

    # ── Confirmation indicator ──────────────────────────────────────────
    conf_code, long_filter, short_filter = _build_confirmation_code(c_type, c_params)
    if conf_code:
        lines.append("// ── Confirmation Indicator ──")
        lines.append(conf_code)
        lines.append("")

    # If filter references confirmation but we didn't build it from c_type, use filter_name
    if filter_name not in ("NONE", "") and not conf_code:
        # Try to build from filter_name itself
        if filter_name in ("PRICE_ABOVE_EMA", "PRICE_BELOW_EMA") and c_type in ("NONE", ""):
            lines.append("// ── Confirmation Indicator ──")
            lines.append("confEma = ta.ema(close, 50)")
            lines.append("")
            long_filter = "close > confEma"
            short_filter = "close < confEma"
        elif filter_name == "VOLUME_ABOVE_SMA":
            lines.append("// ── Confirmation Indicator ──")
            lines.append("confVolSma = ta.sma(volume, 20)")
            lines.append("")
            long_filter = "volume > confVolSma"
            short_filter = "volume > confVolSma"
        elif filter_name == "ATR_EXPANDING":
            long_filter = "atrValue > atrValue[1]"
            short_filter = "atrValue > atrValue[1]"
        elif filter_name == "ADX_TRENDING":
            lines.append("// ── Confirmation Indicator ──")
            lines.append("[confAdxDiPlus, confAdxDiMinus, confAdxValue] = ta.dmi(14, 14)")
            lines.append("")
            long_filter = "confAdxValue > 25"
            short_filter = "confAdxValue > 25"
        elif filter_name == "OBV_RISING":
            lines.append("// ── Confirmation Indicator ──")
            lines.append("confObvValue = ta.obv()")
            lines.append("")
            long_filter = "confObvValue > confObvValue[1]"
            short_filter = "confObvValue > confObvValue[1]"
        else:
            long_filter = "true"
            short_filter = "true"

    # Override from filter_name if it specifically references PRICE_ABOVE/BELOW
    if filter_name == "PRICE_ABOVE_EMA" and conf_code:
        long_filter = "close > confEma"
        short_filter = "close < confEma"
    elif filter_name == "PRICE_BELOW_EMA" and conf_code:
        long_filter = "close < confEma"
        short_filter = "close > confEma"

    # ── ATR for stop/TP (always needed) ─────────────────────────────────
    lines.append("// ── ATR for Stop/TP ──")
    # Don't redeclare if primary is already ATR
    if required_ind != "ATR":
        lines.append("atrValue = ta.atr(14)")
    lines.append("")

    # ── Entry trigger condition ─────────────────────────────────────────
    trigger_expr = get_pine_condition(trigger, p_type)

    lines.append("// ── Entry Conditions ──")
    if direction == "long":
        lines.append(f"longEntry = {trigger_expr} and {long_filter}")
        lines.append("")
    elif direction == "short":
        lines.append(f"shortEntry = {trigger_expr} and {short_filter}")
        lines.append("")
    else:
        lines.append(f"longEntry = {trigger_expr} and {long_filter}")
        lines.append(f"shortEntry = {trigger_expr} and {short_filter}")
        lines.append("")

    # ── Stop loss / take profit computation ─────────────────────────────
    lines.append("// ── Stop Loss & Take Profit ──")

    if direction in ("long", "both"):
        if sl_type == "atr_multiple":
            lines.append(f"longStop = close - atrValue * {sl_value}")
        else:
            # fixed percentage
            lines.append(f"longStop = close * (1 - {sl_value} / 100)")

        if tp_type == "r_multiple":
            if sl_type == "atr_multiple":
                lines.append(f"longTP = close + atrValue * {sl_value} * {tp_value}  // {tp_value}R")
            else:
                lines.append(f"longTP = close + (close - longStop) * {tp_value}  // {tp_value}R")
        else:
            # fixed percentage TP
            lines.append(f"longTP = close * (1 + {tp_value} / 100)")
        lines.append("")

    if direction in ("short", "both"):
        if sl_type == "atr_multiple":
            lines.append(f"shortStop = close + atrValue * {sl_value}")
        else:
            lines.append(f"shortStop = close * (1 + {sl_value} / 100)")

        if tp_type == "r_multiple":
            if sl_type == "atr_multiple":
                lines.append(f"shortTP = close - atrValue * {sl_value} * {tp_value}  // {tp_value}R")
            else:
                lines.append(f"shortTP = close - (shortStop - close) * {tp_value}  // {tp_value}R")
        else:
            lines.append(f"shortTP = close * (1 - {tp_value} / 100)")
        lines.append("")

    # ── Trailing stop / break-even logic ────────────────────────────────
    if trailing_type == "trailing_atr":
        lines.append("// ── Trailing Stop ──")
        lines.append(f"trailOffset = atrValue * {trailing_value}")
        if direction in ("long", "both"):
            lines.append("longTrail = close - trailOffset")
        if direction in ("short", "both"):
            lines.append("shortTrail = close + trailOffset")
        lines.append("")
    elif trailing_type == "break_even":
        lines.append("// ── Break-Even Logic ──")
        lines.append(f"// Move stop to entry after {trailing_trigger_r}R profit is reached")
        lines.append("// (TradingView strategy.exit handles this via trail_offset)")
        lines.append("")

    # ── Time-based exit (bar counter) ───────────────────────────────────
    if time_exit_bars and int(time_exit_bars) > 0:
        lines.append("// ── Time Exit ──")
        lines.append("var int longEntryBar = na")
        lines.append("var int shortEntryBar = na")
        lines.append("")

    # ── Execution ───────────────────────────────────────────────────────
    lines.append("// ── Execution ──")

    if direction in ("long", "both"):
        lines.append("if longEntry")
        lines.append('    strategy.entry("Long", strategy.long)')
        if time_exit_bars and int(time_exit_bars) > 0:
            lines.append("    longEntryBar := bar_index")
        if trailing_type == "trailing_atr":
            lines.append(f'    strategy.exit("Long Exit", "Long", stop=longStop, limit=longTP, trail_points=trailOffset / syminfo.mintick, trail_offset=trailOffset / syminfo.mintick)')
        else:
            lines.append(f'    strategy.exit("Long Exit", "Long", stop=longStop, limit=longTP)')
        lines.append("")

    if direction in ("short", "both"):
        lines.append("if shortEntry")
        lines.append('    strategy.entry("Short", strategy.short)')
        if time_exit_bars and int(time_exit_bars) > 0:
            lines.append("    shortEntryBar := bar_index")
        if trailing_type == "trailing_atr":
            lines.append(f'    strategy.exit("Short Exit", "Short", stop=shortStop, limit=shortTP, trail_points=trailOffset / syminfo.mintick, trail_offset=trailOffset / syminfo.mintick)')
        else:
            lines.append(f'    strategy.exit("Short Exit", "Short", stop=shortStop, limit=shortTP)')
        lines.append("")

    # ── Time-based forced exit ──────────────────────────────────────────
    if time_exit_bars and int(time_exit_bars) > 0:
        te = int(time_exit_bars)
        lines.append("// ── Time-Based Exit ──")
        if direction in ("long", "both"):
            lines.append(f"if not na(longEntryBar) and bar_index - longEntryBar >= {te}")
            lines.append('    strategy.close("Long", comment="Time Exit")')
            lines.append("    longEntryBar := na")
        if direction in ("short", "both"):
            lines.append(f"if not na(shortEntryBar) and bar_index - shortEntryBar >= {te}")
            lines.append('    strategy.close("Short", comment="Time Exit")')
            lines.append("    shortEntryBar := na")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ORB converter: orb_config dict -> Pine Script v5
# ---------------------------------------------------------------------------

def convert_orb_to_pine(orb_config: dict) -> str:
    """Convert an ORB strategy config dict to a complete Pine Script v5 strategy.

    Expected keys in orb_config:
        strategy_id         – str
        range_bars          – int (number of bars forming opening range)
        direction           – "long" | "short" | "both"
        stop_atr_buffer     – float (ATR multiple for stop buffer)
        tp_r_multiple       – float (R-multiple for take profit)
        time_exit_bars      – int (max bars before forced exit)
        session_start_hour  – int (default 9)
        session_start_minute – int (default 30)
    """
    sid = orb_config.get("strategy_id", "ORB_Strategy")
    range_bars = orb_config.get("range_bars", 2)
    direction = orb_config.get("direction", "long")
    stop_atr_buffer = orb_config.get("stop_atr_buffer", 0.25)
    tp_r = orb_config.get("tp_r_multiple", 2.0)
    time_exit_bars = orb_config.get("time_exit_bars", 16)
    sess_hour = orb_config.get("session_start_hour", 9)
    sess_min = orb_config.get("session_start_minute", 30)

    # Format session start time as "HH:MM"
    sess_start = f"{sess_hour:02d}:{sess_min:02d}"

    lines: list[str] = []

    # Header
    lines.append("//@version=5")
    lines.append(f'strategy("StrategyLab ORB: {sid}", overlay=true, initial_capital=50000,')
    lines.append('         default_qty_type=strategy.percent_of_equity, default_qty_value=0.25,')
    lines.append('         commission_type=strategy.commission.percent, commission_value=0.05)')
    lines.append("")

    # Inputs
    lines.append("// ── Inputs ──")
    lines.append(f"rangeBars      = input.int({range_bars}, 'Opening Range Bars')")
    lines.append(f"stopAtrBuffer  = input.float({stop_atr_buffer}, 'Stop ATR Buffer')")
    lines.append(f"tpRMultiple    = input.float({tp_r}, 'Take Profit R-Multiple')")
    lines.append(f"timeExitBars   = input.int({time_exit_bars}, 'Time Exit (bars)')")
    lines.append("")

    # Session detection
    lines.append("// ── Session Detection ──")
    lines.append(f'isSessionStart = (hour == {sess_hour} and minute == {sess_min})')
    lines.append("")

    # Opening range tracking
    lines.append("// ── Opening Range Tracking ──")
    lines.append("var float rangeHigh = na")
    lines.append("var float rangeLow  = na")
    lines.append("var int   rangeCnt  = 0")
    lines.append("var bool  rangeSet  = false")
    lines.append("var int   entryBar  = na")
    lines.append("")
    lines.append("// Reset on new session")
    lines.append("if isSessionStart and rangeCnt == 0")
    lines.append("    rangeHigh := high")
    lines.append("    rangeLow  := low")
    lines.append("    rangeCnt  := 1")
    lines.append("    rangeSet  := false")
    lines.append("")
    lines.append("// Accumulate range bars")
    lines.append("if rangeCnt > 0 and rangeCnt < rangeBars and not rangeSet")
    lines.append("    rangeHigh := math.max(rangeHigh, high)")
    lines.append("    rangeLow  := math.min(rangeLow,  low)")
    lines.append("    rangeCnt  += 1")
    lines.append("")
    lines.append("// Lock range once all bars collected")
    lines.append("if rangeCnt >= rangeBars and not rangeSet")
    lines.append("    rangeSet := true")
    lines.append("")

    # Plot range
    lines.append("// ── Plot Range ──")
    lines.append("plot(rangeSet ? rangeHigh : na, 'Range High', color=color.green, style=plot.style_linebr)")
    lines.append("plot(rangeSet ? rangeLow  : na, 'Range Low',  color=color.red,   style=plot.style_linebr)")
    lines.append("")

    # ATR
    lines.append("// ── ATR ──")
    lines.append("atrValue = ta.atr(14)")
    lines.append("")

    # Entry conditions
    lines.append("// ── Entry Conditions ──")
    lines.append("noPosition = strategy.position_size == 0")
    lines.append("")

    if direction in ("long", "both"):
        lines.append("longBreakout = rangeSet and close > rangeHigh and noPosition")
        lines.append("if longBreakout")
        lines.append('    strategy.entry("Long", strategy.long)')
        lines.append("    entryBar := bar_index")
        lines.append("    longStopPrice = rangeLow - stopAtrBuffer * atrValue")
        lines.append("    longRisk = close - longStopPrice")
        lines.append("    longTPPrice = close + longRisk * tpRMultiple")
        lines.append('    strategy.exit("Long Exit", "Long", stop=longStopPrice, limit=longTPPrice)')
        lines.append("    // Invalidate range so we don't re-enter")
        lines.append("    rangeCnt := 0")
        lines.append("    rangeSet := false")
        lines.append("")

    if direction in ("short", "both"):
        lines.append("shortBreakout = rangeSet and close < rangeLow and noPosition")
        lines.append("if shortBreakout")
        lines.append('    strategy.entry("Short", strategy.short)')
        lines.append("    entryBar := bar_index")
        lines.append("    shortStopPrice = rangeHigh + stopAtrBuffer * atrValue")
        lines.append("    shortRisk = shortStopPrice - close")
        lines.append("    shortTPPrice = close - shortRisk * tpRMultiple")
        lines.append('    strategy.exit("Short Exit", "Short", stop=shortStopPrice, limit=shortTPPrice)')
        lines.append("    rangeCnt := 0")
        lines.append("    rangeSet := false")
        lines.append("")

    # Time exit
    if time_exit_bars and int(time_exit_bars) > 0:
        lines.append("// ── Time-Based Exit ──")
        lines.append(f"if not na(entryBar) and bar_index - entryBar >= timeExitBars")
        if direction in ("long", "both"):
            lines.append('    strategy.close("Long", comment="Time Exit")')
        if direction in ("short", "both"):
            lines.append('    strategy.close("Short", comment="Time Exit")')
        lines.append("    entryBar := na")
        lines.append("")

    # Reset range at end of day (avoid carryover)
    lines.append("// ── End-of-Day Reset ──")
    lines.append("if ta.change(time('D'))")
    lines.append("    rangeCnt := 0")
    lines.append("    rangeSet := false")
    lines.append("    rangeHigh := na")
    lines.append("    rangeLow  := na")
    lines.append("")

    return "\n".join(lines)
