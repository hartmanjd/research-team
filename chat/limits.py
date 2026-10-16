"""Limits for the public Ask page: a daily spend cap shared by all visitors, and per-visitor rate limits.

The spend cap holds back a reserve when a question starts and settles it to the real cost when the
answer is done, so several questions at once cannot run past the cap by more than a few cents. The day
resets at midnight UTC. Spending is saved to a small JSON file so a restart of the same server keeps it;
a fresh server (a redeploy) starts the day at zero, so also set a monthly limit on the API key itself.
"""
import json, os, threading, time
from collections import deque
from datetime import datetime, timezone

DAILY_CAP_USD = float(os.environ.get("CHAT_DAILY_CAP_USD", "3"))
RESERVE_USD = 0.02  # held per question while it runs; answers in the eval cost $0.0002 to $0.002
PER_MINUTE = int(os.environ.get("CHAT_PER_MINUTE", "5"))
PER_DAY = int(os.environ.get("CHAT_PER_DAY", "40"))


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class SpendCap:
    def __init__(self, cap_usd=DAILY_CAP_USD, path=None, clock=today):
        self.cap, self.path, self.clock = cap_usd, path, clock
        self.lock = threading.Lock()
        self.day, self.spent, self.held = clock(), 0.0, 0.0
        if path and os.path.exists(path):
            try:
                saved = json.load(open(path))
                if saved.get("day") == self.day:
                    self.spent = float(saved.get("spent_usd", 0))
            except (OSError, ValueError):
                pass

    def _roll(self):
        if self.clock() != self.day:
            self.day, self.spent = self.clock(), 0.0

    def reserve(self, amount=RESERVE_USD):
        """Hold `amount` for a question; False when that would pass today's cap."""
        with self.lock:
            self._roll()
            if self.spent + self.held + amount > self.cap:
                return False
            self.held += amount
            return True

    def settle(self, cost, amount=RESERVE_USD):
        """Swap a held reserve for the question's real cost."""
        with self.lock:
            self._roll()
            self.held = max(0.0, self.held - amount)
            self.spent += cost
            if self.path:
                try:
                    with open(self.path, "w") as f:
                        json.dump({"day": self.day, "spent_usd": round(self.spent, 6)}, f)
                except OSError:
                    pass

    def left(self):
        with self.lock:
            self._roll()
            return max(0.0, self.cap - self.spent - self.held)


class RateLimit:
    """At most `per_minute` questions in any 60 seconds and `per_day` in any 24 hours, per visitor."""

    def __init__(self, per_minute=PER_MINUTE, per_day=PER_DAY, clock=time.time):
        self.per_minute, self.per_day, self.clock = per_minute, per_day, clock
        self.lock = threading.Lock()
        self.seen = {}

    def check(self, visitor):
        """Record a question; return None when allowed, or a message saying when to try again."""
        now = self.clock()
        with self.lock:
            q = self.seen.setdefault(visitor, deque())
            while q and now - q[0] > 86400:
                q.popleft()
            if len(q) >= self.per_day:
                return f"You've asked {self.per_day} questions today. Please come back tomorrow."
            if sum(1 for t in q if now - t <= 60) >= self.per_minute:
                return "That's a lot of questions in a minute. Please wait a moment and try again."
            q.append(now)
            if len(self.seen) > 10000:  # drop visitors with nothing in the last day
                for k in [k for k, v in self.seen.items() if not v or now - v[-1] > 86400]:
                    del self.seen[k]
            return None
