import unittest

from api_protection import LimitRule, SlidingWindowRateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now


class SlidingWindowRateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.limiter = SlidingWindowRateLimiter(clock=self.clock)

    def test_blocks_after_limit_and_allows_after_window(self):
        rule = LimitRule("generate:client:test", limit=2, window_seconds=60)

        self.assertTrue(self.limiter.check([rule]).allowed)
        self.assertTrue(self.limiter.check([rule]).allowed)
        blocked = self.limiter.check([rule])
        self.assertFalse(blocked.allowed)
        self.assertGreaterEqual(blocked.retry_after, 60)

        self.clock.now = 61
        self.assertTrue(self.limiter.check([rule]).allowed)

    def test_global_failure_does_not_consume_client_allowance(self):
        client_rule = LimitRule("generate:client:test", limit=2, window_seconds=60)
        global_rule = LimitRule("generate:global", limit=1, window_seconds=60)

        self.assertTrue(self.limiter.check([client_rule, global_rule]).allowed)
        self.assertFalse(self.limiter.check([client_rule, global_rule]).allowed)

        self.clock.now = 61
        self.assertTrue(self.limiter.check([client_rule, global_rule]).allowed)


if __name__ == "__main__":
    unittest.main()
