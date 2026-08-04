from app.options.black_scholes import OptionGreeks, value


def greeks(*args, **kwargs) -> OptionGreeks:
    return value(*args, **kwargs).greeks
