"""Retry helpers shared by HTTP clients (FNSI, GitLab)."""

import random

DEFAULT_RETRY_DELAY = 2  # base delay between attempts, seconds
MAX_RETRY_DELAY = 30  # upper bound for a single delay, seconds


def backoff_delay(attempt: int, base_delay: float = DEFAULT_RETRY_DELAY) -> float:
    """Exponential backoff with up to 1s of jitter.

    Args:
        attempt: 1-based number of the attempt that just failed.
        base_delay: delay after the first failed attempt, seconds.

    Returns:
        Delay in seconds before the next attempt.
    """
    base = base_delay * (2 ** (attempt - 1))
    return min(base, MAX_RETRY_DELAY) + random.uniform(0, 1)
