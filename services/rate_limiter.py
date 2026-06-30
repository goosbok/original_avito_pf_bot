"""Глобальный ограничитель темпа отправок в biza (token bucket).

biza режет при >60 запросов/мин (HTTP 429). Лимитер раздаёт «слоты» с
постоянной скоростью; acquire() блокирует вызывающего, пока слот не освободится.
Один процесс-синглтон — общий для диспетчера, force_dispatch и ручных прогонов.
Часы/сон инъектируются для тестов.
"""
from __future__ import annotations

import threading
import time

from data import config


class RateLimiter:
    def __init__(self, max_per_minute: int, *, monotonic=time.monotonic, sleep=time.sleep):
        self._capacity = float(max(1, int(max_per_minute)))
        self._refill_per_sec = self._capacity / 60.0
        self._tokens = self._capacity
        self._monotonic = monotonic
        self._sleep = sleep
        self._last = monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._monotonic()
                self._tokens = min(
                    self._capacity,
                    self._tokens + (now - self._last) * self._refill_per_sec,
                )
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._refill_per_sec
            self._sleep(wait)

    def reset(self) -> None:
        with self._lock:
            self._tokens = self._capacity
            self._last = self._monotonic()


_limiter = RateLimiter(config.BIZA_MAX_PER_MIN)


def acquire() -> None:
    _limiter.acquire()


def reset() -> None:
    _limiter.reset()
