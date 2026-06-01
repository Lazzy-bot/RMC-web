"""
rate_limiter.py — Sliding Window Counter Rate Limiter

Thuật toán: Sliding Window Counter
  - Chính xác hơn Fixed Window (không bị spike ở ranh giới window)
  - Nhẹ hơn Token Bucket / Leaky Bucket
  - In-memory, thread-safe với threading.Lock
  - Tự dọn dẹp entries cũ để tránh memory leak

Usage:
    from rate_limiter import login_limiter, api_limiter
    allowed, retry_after = login_limiter.is_allowed("192.168.1.1")
    if not allowed:
        return jsonify({"error": "Rate limited"}), 429
"""

import time
import threading
import os
from collections import deque
from typing import Tuple


# ---------------------------------------------------------------------------
# Core Class
# ---------------------------------------------------------------------------

class SlidingWindowRateLimiter:
    """
    Thread-safe Sliding Window Rate Limiter.

    Args:
        max_calls (int):      Số request tối đa trong 1 window period.
        period (int):         Độ dài window tính bằng giây.
        block_duration (int): Thời gian block (giây) sau khi vượt limit.
                              Nếu = 0, chỉ reject request hiện tại, không block thêm.
        name (str):           Tên limiter (dùng cho logging/stats).
    """

    def __init__(self, max_calls: int, period: int, block_duration: int = 0, name: str = ""):
        self.max_calls = max_calls
        self.period = period
        self.block_duration = block_duration
        self.name = name

        # { key: deque([timestamp, ...]) }  — timestamps của các request gần đây
        self._windows: dict[str, deque] = {}
        # { key: float }  — thời điểm block hết hạn (epoch seconds)
        self._blocked_until: dict[str, float] = {}

        self._lock = threading.Lock()
        self._last_cleanup = time.time()
        self._cleanup_interval = max(period * 2, 120)  # Dọn tối thiểu mỗi 2 phút

        # Stats
        self._total_allowed = 0
        self._total_blocked = 0

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """
        Kiểm tra xem key có được phép gửi request không.

        Returns:
            (allowed: bool, retry_after: int)
            retry_after = 0 nếu được phép, > 0 là số giây phải chờ.
        """
        now = time.time()

        with self._lock:
            self._maybe_cleanup(now)

            # 1. Kiểm tra block cứng
            blocked_until = self._blocked_until.get(key, 0)
            if now < blocked_until:
                retry_after = int(blocked_until - now) + 1
                self._total_blocked += 1
                return False, retry_after

            # 2. Sliding window: xóa timestamps đã cũ hơn `period`
            window = self._windows.setdefault(key, deque())
            cutoff = now - self.period
            while window and window[0] <= cutoff:
                window.popleft()

            # 3. Kiểm tra giới hạn
            if len(window) >= self.max_calls:
                # Tính retry_after: khi nào timestamp cũ nhất sẽ expire
                oldest_ts = window[0]
                retry_after = int(oldest_ts + self.period - now) + 1

                # Áp dụng block cứng nếu block_duration > 0
                if self.block_duration > 0:
                    self._blocked_until[key] = now + self.block_duration
                    retry_after = self.block_duration

                self._total_blocked += 1
                return False, retry_after

            # 4. Cho phép — ghi nhận timestamp
            window.append(now)
            self._total_allowed += 1
            return True, 0

    def get_remaining(self, key: str) -> int:
        """Trả về số request còn lại trong window hiện tại."""
        now = time.time()
        with self._lock:
            window = self._windows.get(key, deque())
            cutoff = now - self.period
            active = sum(1 for ts in window if ts > cutoff)
            return max(0, self.max_calls - active)

    def get_reset_time(self, key: str) -> int:
        """Trả về epoch timestamp khi window reset."""
        with self._lock:
            window = self._windows.get(key)
            if window:
                return int(window[0] + self.period)
            return int(time.time() + self.period)

    def reset_key(self, key: str) -> None:
        """Xóa toàn bộ lịch sử và block cho một key cụ thể."""
        with self._lock:
            self._windows.pop(key, None)
            self._blocked_until.pop(key, None)

    def get_stats(self) -> dict:
        """Trả về thống kê tổng quan của limiter này."""
        with self._lock:
            now = time.time()
            active_keys = len(self._windows)
            blocked_keys = sum(1 for t in self._blocked_until.values() if t > now)
            return {
                "name": self.name,
                "max_calls": self.max_calls,
                "period": self.period,
                "block_duration": self.block_duration,
                "active_keys": active_keys,
                "blocked_keys": blocked_keys,
                "total_allowed": self._total_allowed,
                "total_blocked": self._total_blocked,
                "blocked_ips": [
                    {"key": k, "retry_after": int(v - now)}
                    for k, v in self._blocked_until.items()
                    if v > now
                ],
            }

    # -----------------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------------

    def _maybe_cleanup(self, now: float) -> None:
        """Dọn dẹp entries cũ định kỳ (gọi trong lock context)."""
        if now - self._last_cleanup < self._cleanup_interval:
            return

        cutoff = now - self.period
        # Xóa windows rỗng
        dead_keys = [k for k, w in self._windows.items() if not w or w[-1] <= cutoff]
        for k in dead_keys:
            del self._windows[k]

        # Xóa blocks đã hết hạn
        expired_blocks = [k for k, t in self._blocked_until.items() if t <= now]
        for k in expired_blocks:
            del self._blocked_until[k]

        self._last_cleanup = now


# ---------------------------------------------------------------------------
# Pre-configured Limiter Instances
# Đọc giá trị từ environment variables với fallback mặc định.
# ---------------------------------------------------------------------------

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


# Brute-force protection cho login endpoint (per IP)
login_limiter = SlidingWindowRateLimiter(
    max_calls=_env_int("RATE_LIMIT_LOGIN_MAX", 5),
    period=_env_int("RATE_LIMIT_LOGIN_PERIOD", 60),
    block_duration=_env_int("RATE_LIMIT_LOGIN_BLOCK", 300),  # 5 phút
    name="login",
)

# Global API limit per IP (tất cả /api/* endpoints)
api_ip_limiter = SlidingWindowRateLimiter(
    max_calls=_env_int("RATE_LIMIT_API_MAX", 100),
    period=_env_int("RATE_LIMIT_API_PERIOD", 60),
    block_duration=_env_int("RATE_LIMIT_API_BLOCK", 60),
    name="api_ip",
)

# Global API limit per authenticated user
api_user_limiter = SlidingWindowRateLimiter(
    max_calls=_env_int("RATE_LIMIT_USER_MAX", 200),
    period=_env_int("RATE_LIMIT_API_PERIOD", 60),
    block_duration=0,  # không block user, chỉ throttle
    name="api_user",
)

# Heavy / expensive operations (sync, charts, dashboard, report read)
heavy_limiter = SlidingWindowRateLimiter(
    max_calls=_env_int("RATE_LIMIT_HEAVY_MAX", 10),
    period=_env_int("RATE_LIMIT_HEAVY_PERIOD", 60),
    block_duration=_env_int("RATE_LIMIT_HEAVY_BLOCK", 120),
    name="heavy",
)



# OneDrive sync trigger — rất tốn kém (per IP)
sync_limiter = SlidingWindowRateLimiter(
    max_calls=_env_int("RATE_LIMIT_SYNC_MAX", 3),
    period=_env_int("RATE_LIMIT_SYNC_PERIOD", 300),  # 5 phút
    block_duration=_env_int("RATE_LIMIT_SYNC_BLOCK", 600),  # 10 phút
    name="sync",
)

# Admin management endpoints (per IP)
admin_limiter = SlidingWindowRateLimiter(
    max_calls=_env_int("RATE_LIMIT_ADMIN_MAX", 30),
    period=_env_int("RATE_LIMIT_ADMIN_PERIOD", 60),
    block_duration=_env_int("RATE_LIMIT_ADMIN_BLOCK", 120),
    name="admin",
)

# Danh sách tất cả limiters để stats endpoint dùng
ALL_LIMITERS = [
    login_limiter,
    api_ip_limiter,
    api_user_limiter,
    heavy_limiter,
    sync_limiter,
    admin_limiter,
]
