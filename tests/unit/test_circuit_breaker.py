"""CircuitBreaker: открывается после N ошибок подряд, держит cooldown, успех закрывает."""
from services.circuit_breaker import CircuitBreaker


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t


def test_opens_after_max_consecutive_errors():
    clk = FakeClock()
    cb = CircuitBreaker(3, cooldown_seconds=100, monotonic=clk.monotonic)
    assert cb.allow() is True
    cb.record_error(); cb.record_error()
    assert cb.allow() is True            # 2 < 3 — ещё закрыт
    cb.record_error()                    # 3-я → открывается
    assert cb.allow() is False


def test_cooldown_expires():
    clk = FakeClock()
    cb = CircuitBreaker(1, cooldown_seconds=100, monotonic=clk.monotonic)
    cb.record_error()                    # открылся в t=0 до t=100
    assert cb.allow() is False
    clk.t = 100.0
    assert cb.allow() is True            # cooldown истёк


def test_success_resets_consecutive():
    clk = FakeClock()
    cb = CircuitBreaker(3, cooldown_seconds=100, monotonic=clk.monotonic)
    cb.record_error(); cb.record_error()
    cb.record_success()                  # сброс
    cb.record_error(); cb.record_error()
    assert cb.allow() is True            # снова только 2 подряд
