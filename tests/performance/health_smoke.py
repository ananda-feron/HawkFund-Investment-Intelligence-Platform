#!/usr/bin/env python3
import argparse
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def request(url: str) -> float:
    started = time.perf_counter()
    with urllib.request.urlopen(url, timeout=3) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected response status {response.status}")
    return (time.perf_counter() - started) * 1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/health/live")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--p95-ms", type=float, default=250)
    arguments = parser.parse_args()

    with ThreadPoolExecutor(max_workers=arguments.concurrency) as pool:
        latencies = list(pool.map(request, [arguments.url] * arguments.requests))
    p95 = statistics.quantiles(latencies, n=100)[94]
    print(
        f"requests={len(latencies)} p50_ms={statistics.median(latencies):.2f} "
        f"p95_ms={p95:.2f} max_ms={max(latencies):.2f}"
    )
    if p95 > arguments.p95_ms:
        raise SystemExit(f"p95 {p95:.2f}ms exceeded {arguments.p95_ms:.2f}ms threshold")


if __name__ == "__main__":
    main()
