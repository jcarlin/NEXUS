"""Static model pricing for cost estimation.

Prices are per 1M tokens (input, output). Updated periodically.
"""

# (input_price_per_1M, output_price_per_1M)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-sonnet-4-5-20250929": (3.0, 15.0),
    "claude-haiku-3-5-20241022": (0.80, 4.0),
    "claude-opus-4-20250514": (15.0, 75.0),
    "claude-sonnet-4-6-20260320": (3.0, 15.0),
    # OpenAI
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "o3-mini": (1.10, 4.40),
    # Gemini
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-pro-preview-06-05": (1.25, 10.0),
    "gemini-2.5-flash-preview-05-20": (0.15, 0.60),
    # Ollama (free, local)
    "ollama": (0.0, 0.0),
}


def get_model_pricing(model: str) -> tuple[float, float]:
    """Return (input_price, output_price) per 1M tokens for a model.

    Falls back to (0, 0) for unknown models (including Ollama).
    """
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # Fuzzy match: check if any key is a substring
    for key, price in MODEL_PRICING.items():
        if key in model or model in key:
            return price
    return (0.0, 0.0)
