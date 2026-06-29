"""Стоп-кран для отправок в biza.

Считает ошибки подряд; после max_consecutive_errors открывается и держит
cooldown (allow()==False). Любой успех закрывает. Состояние in-process —
при рестарте сбрасывается (допустимо). Часы инъектируются для тестов.
"""
from __future__ import annotations

import threading
import time


class CircuitBreaker:
    def __init__(self, max_consecutive_errors: int, cooldown_seconds: float,
                 *, monotonic=time.monotonic):
        self._max = max(1, int(max_consecutive_errors))
        self._cooldown = float(cooldown_seconds)
        self._monotonic = monotonic
        self._consecutive = 0
        self._open_until = 0.0
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            return self._monotonic() >= self._open_until

    def record_error(self) -> None:
        with self._lock:
            self._consecutive += 1
            if self._consecutive >= self._max:
                self._open_until = self._monotonic() + self._cooldown

    def record_success(self) -> None:
        with self._lock:
            self._consecutive = 0
            self._open_until = 0.0

    def reset(self) -> None:
        with self._lock:
            self._consecutive = 0
            self._open_until = 0.0
