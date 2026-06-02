"""Shared SlowAPI limiter for REST and webhook endpoints."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    application_limits=["60/minute"],
)
