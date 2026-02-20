"""
Function decoration for backoff and retry

This module provides function decorators which can be used to wrap a
function such that it will be retried until some condition is met. It
is meant to be of use when accessing unreliable resources with the
potential for intermittent failures i.e. network resources and external
APIs. Somewhat more generally, it may also be of use for dynamically
polling resources for externally generated content.

For examples and full documentation see the README at
https://github.com/python-backoff/backoff
"""

from backoff._decorator import on_exception, on_predicate
from backoff._jitter import full_jitter, random_jitter
from backoff._wait_gen import constant, decay, expo, fibo, runtime

__all__ = [
    "constant",
    "decay",
    "expo",
    "fibo",
    "full_jitter",
    "on_exception",
    "on_predicate",
    "random_jitter",
    "runtime",
]

__version__ = "2.3.1"
