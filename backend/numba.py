"""
numba.py — Pure-Python no-op shim for `numba` on Python 3.14.

WHY THIS EXISTS:
  pandas_ta (our technical-indicator library) does `from numba import njit` and
  decorates a handful of helper functions with `@njit(cache=True)` for JIT speed.
  The real `numba` has no Python 3.14 wheels and will not build on 3.14, which
  blocked `import pandas_ta` entirely.

  numba is purely a performance accelerator here — the decorated functions are
  ordinary Python that compute the same result without JIT. This shim provides
  no-op `njit` / `jit` decorators and a `prange` alias so pandas_ta imports and
  runs in pure Python (a little slower, only during the one-time feature build).

SAFETY:
  Only loaded because no real `numba` is installed (3.14). If you move to a
  supported Python (3.11) and install the real numba, delete this file so the
  genuine, JIT-compiled numba is used instead.
"""

prange = range


def njit(*args, **kwargs):
    """No-op stand-in for numba.njit. Supports both `@njit` and `@njit(cache=True)`."""
    # Bare usage: @njit
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]

    # Parametrized usage: @njit(cache=True)
    def decorator(func):
        return func

    return decorator


# `jit` is an alias of the same behaviour for any code that asks for it.
jit = njit
