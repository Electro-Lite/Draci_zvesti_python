import time
import random
import functools
import logging

from typing import Callable, Type, Tuple, Optional

# Module-level defaults you can tweak in one place
DEFAULT_RETRIES = 3
DEFAULT_BASE_DELAY = 0.1
DEFAULT_BACKOFF = 2.0
DEFAULT_JITTER = 0.1
DEFAULT_EXCEPTIONS: Tuple[Type[BaseException], ...] = (Exception,)

_logger = logging.getLogger(__name__)

def retry(
    _func: Optional[Callable] = None,
    *,
    retries: int = DEFAULT_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    backoff: float = DEFAULT_BACKOFF,
    jitter: float = DEFAULT_JITTER,
    exceptions: Tuple[Type[BaseException], ...] = DEFAULT_EXCEPTIONS,
    logger: Optional[logging.Logger] = None,
):
    """
    Retry decorator with exponential backoff + jitter.
    Can be used as:
        @retry
        def f(...): ...
    or
        @retry()
        def f(...): ...
    or
        @retry(retries=5, jitter=0.2)
        def f(...): ...

    Args:
        retries: total attempts (default 3).
        base_delay: initial delay in seconds.
        backoff: multiplier for exponential backoff.
        jitter: max random jitter added (uniform(0, jitter)).
        exceptions: tuple of exception classes to catch and retry on.
        logger: optional logger (defaults to module logger).
    """
    if logger is None:
        logger = _logger

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    # final attempt -> re-raise
                    if attempt == retries:
                        if logger:
                            logger.exception(
                                "Function %s failed on final attempt %d/%d: %s",
                                func.__qualname__, attempt, retries, exc
                            )
                        raise
                    delay = base_delay * (backoff ** (attempt - 1))
                    delay += random.uniform(0, jitter)
                    if logger:
                        logger.warning(
                            "Retrying %s (attempt %d/%d) after %.3fs due to %s",
                            func.__qualname__, attempt, retries, delay, exc
                        )
                    time.sleep(delay)
            # fallback (shouldn't happen)
            if last_exc:
                raise last_exc
        return wrapper

    # If decorator used without arguments: @retry
    if _func is not None and callable(_func):
        return decorator(_func)

    # Otherwise return the decorator configured with provided kwargs
    return decorator