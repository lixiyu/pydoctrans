"""Prometheus 指标模块。

暴露转换服务的运行时指标，供 Prometheus 抓取。
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ---- 请求指标 ----
requests_total = Counter(
    "pydoctrans_requests_total",
    "转换请求总数",
    ["status", "format"],
)

request_duration_seconds = Histogram(
    "pydoctrans_request_duration_seconds",
    "转换请求耗时（秒）",
    ["format"],
    buckets=[1, 5, 10, 30, 60, 120, 300],
)

# ---- 文件指标 ----
file_size_bytes = Histogram(
    "pydoctrans_file_size_bytes",
    "上传文件大小",
    buckets=[
        1024,           # 1 KB
        10240,          # 10 KB
        102400,         # 100 KB
        1048576,        # 1 MB
        10485760,       # 10 MB
        52428800,       # 50 MB
    ],
)

# ---- 池指标 ----
pool_slots_available = Gauge(
    "pydoctrans_pool_slots_available",
    "当前可用转换槽位数",
)

pool_slots_max = Gauge(
    "pydoctrans_pool_slots_max",
    "转换槽位总数",
)

pool_slots_in_use = Gauge(
    "pydoctrans_pool_slots_in_use",
    "当前正在使用的转换槽位数",
)

# ---- 运行中请求 ----
requests_in_flight = Gauge(
    "pydoctrans_requests_in_flight",
    "当前正在处理的请求数",
)
