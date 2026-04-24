import config


def passes_volatility_filter(symbol: str, atr_value: float) -> bool:
    """
    Returns False if ATR is below minimum threshold (too quiet) or
    above spike threshold (news event / abnormal volatility).
    """
    threshold = config.ATR_MIN_THRESHOLD.get(symbol, config.ATR_MIN_THRESHOLD.get("_default", 0.0))
    if threshold <= 0:
        return True
    if atr_value < threshold:
        return False
    if atr_value > threshold * config.ATR_SPIKE_MULTIPLIER:
        return False
    return True
