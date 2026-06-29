"""Token-bucket RateLimiter: не выдаёт больше ёмкости за окно, распределяет во времени."""
from services.rate_limiter import RateLimiter


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.slept = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, dur):
        # эмулируем течение времени вместо реального ожидания
        self.slept += dur
        self.t += dur


def test_initial_burst_up_to_capacity_is_instant():
    clk = FakeClock()
    rl = RateLimiter(60, monotonic=clk.monotonic, sleep=clk.sleep)
    for _ in range(60):
        rl.acquire()
    assert clk.slept == 0.0  # стартовый бакет полон → первые 60 мгновенно


def test_over_capacity_waits_for_refill():
    clk = FakeClock()
    rl = RateLimiter(60, monotonic=clk.monotonic, sleep=clk.sleep)
    for _ in range(60):
        rl.acquire()
    rl.acquire()  # 61-й — должен подождать ~1с (60/мин = 1 токен/сек)
    assert abs(clk.slept - 1.0) < 1e-6


def test_reset_refills_bucket():
    clk = FakeClock()
    rl = RateLimiter(60, monotonic=clk.monotonic, sleep=clk.sleep)
    for _ in range(60):
        rl.acquire()
    rl.reset()
    rl.acquire()  # снова мгновенно
    assert clk.slept == 0.0
