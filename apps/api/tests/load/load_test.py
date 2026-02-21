#!/usr/bin/env python3
"""
Continuum API Load Test Script (Python)

A pure Python load testing script that doesn't require external tools.
Uses asyncio and aiohttp for concurrent requests.

Target: 50 RPS with <500ms p99 latency

Usage:
    # Run from the api directory with virtual environment activated:
    cd apps/api
    .venv/bin/python tests/load/load_test.py

    # With custom options:
    .venv/bin/python tests/load/load_test.py --rps 50 --duration 60 --base-url http://localhost:8000

Requirements:
    pip install aiohttp  # Should already be in requirements
"""

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None  # Will be checked at runtime


@dataclass
class EndpointMetrics:
    """Metrics for a single endpoint."""

    name: str
    latencies: list[float] = field(default_factory=list)
    successes: int = 0
    failures: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_requests(self) -> int:
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successes / self.total_requests * 100

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.failures / self.total_requests * 100

    def percentile(self, p: float) -> float:
        """Calculate the p-th percentile of latencies."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * p / 100)
        return sorted_latencies[min(index, len(sorted_latencies) - 1)]

    @property
    def p50(self) -> float:
        return self.percentile(50)

    @property
    def p95(self) -> float:
        return self.percentile(95)

    @property
    def p99(self) -> float:
        return self.percentile(99)

    @property
    def avg(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies)

    @property
    def min(self) -> float:
        if not self.latencies:
            return 0.0
        return min(self.latencies)

    @property
    def max(self) -> float:
        if not self.latencies:
            return 0.0
        return max(self.latencies)


@dataclass
class LoadTestResults:
    """Aggregated load test results."""

    start_time: datetime
    end_time: Optional[datetime] = None
    endpoints: dict[str, EndpointMetrics] = field(default_factory=dict)
    target_rps: int = 50
    target_p99_ms: int = 500

    @property
    def duration_seconds(self) -> float:
        if not self.end_time:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()

    @property
    def total_requests(self) -> int:
        return sum(e.total_requests for e in self.endpoints.values())

    @property
    def actual_rps(self) -> float:
        if self.duration_seconds == 0:
            return 0.0
        return self.total_requests / self.duration_seconds

    @property
    def overall_success_rate(self) -> float:
        total = sum(e.total_requests for e in self.endpoints.values())
        successes = sum(e.successes for e in self.endpoints.values())
        if total == 0:
            return 0.0
        return successes / total * 100

    @property
    def all_latencies(self) -> list[float]:
        latencies = []
        for e in self.endpoints.values():
            latencies.extend(e.latencies)
        return latencies

    @property
    def overall_p99(self) -> float:
        latencies = self.all_latencies
        if not latencies:
            return 0.0
        sorted_latencies = sorted(latencies)
        index = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(index, len(sorted_latencies) - 1)]

    def passed(self) -> bool:
        """Check if the test passed the target thresholds."""
        return (
            self.overall_p99 < self.target_p99_ms and self.overall_success_rate > 99.0
        )


# Sample search queries
SEARCH_QUERIES = [
    "PostgreSQL",
    "authentication",
    "database",
    "API",
    "architecture",
    "security",
    "performance",
    "testing",
    "deployment",
    "monitoring",
]


class LoadTester:
    """Async load tester for Continuum API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        target_rps: int = 50,
        duration_seconds: int = 60,
        ramp_up_seconds: int = 10,
    ):
        self.base_url = base_url.rstrip("/")
        self.target_rps = target_rps
        self.duration_seconds = duration_seconds
        self.ramp_up_seconds = ramp_up_seconds
        self.results = LoadTestResults(
            start_time=datetime.now(),
            target_rps=target_rps,
        )

        # Initialize endpoint metrics
        for name in ["decisions", "graph", "hybrid_search", "dashboard_stats"]:
            self.results.endpoints[name] = EndpointMetrics(name=name)

    async def check_health(self, session: aiohttp.ClientSession) -> bool:
        """Check if the API is healthy."""
        try:
            async with session.get(f"{self.base_url}/health") as response:
                return response.status == 200
        except Exception as e:
            print(f"Health check failed: {e}")
            return False

    async def test_decisions(self, session: aiohttp.ClientSession) -> None:
        """Test GET /api/decisions endpoint."""
        metrics = self.results.endpoints["decisions"]
        limit = random.randint(10, 60)
        offset = random.randint(0, 5) * 10

        url = f"{self.base_url}/api/decisions?limit={limit}&offset={offset}"

        start = time.perf_counter()
        try:
            async with session.get(url) as response:
                latency = (time.perf_counter() - start) * 1000  # Convert to ms
                metrics.latencies.append(latency)

                if response.status == 200:
                    body = await response.json()
                    if isinstance(body, list):
                        metrics.successes += 1
                    else:
                        metrics.failures += 1
                        metrics.errors.append("Invalid response format")
                else:
                    metrics.failures += 1
                    metrics.errors.append(f"Status {response.status}")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            metrics.latencies.append(latency)
            metrics.failures += 1
            metrics.errors.append(str(e))

    async def test_graph(self, session: aiohttp.ClientSession) -> None:
        """Test GET /api/graph endpoint."""
        metrics = self.results.endpoints["graph"]

        # 80% paginated, 20% full
        if random.random() < 0.8:
            page = random.randint(1, 3)
            page_size = random.randint(50, 100)
            url = f"{self.base_url}/api/graph?page={page}&page_size={page_size}"
        else:
            url = f"{self.base_url}/api/graph/all"

        start = time.perf_counter()
        try:
            async with session.get(url) as response:
                latency = (time.perf_counter() - start) * 1000
                metrics.latencies.append(latency)

                if response.status == 200:
                    body = await response.json()
                    if "nodes" in body and "edges" in body:
                        metrics.successes += 1
                    else:
                        metrics.failures += 1
                        metrics.errors.append("Missing nodes or edges")
                else:
                    metrics.failures += 1
                    metrics.errors.append(f"Status {response.status}")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            metrics.latencies.append(latency)
            metrics.failures += 1
            metrics.errors.append(str(e))

    async def test_hybrid_search(self, session: aiohttp.ClientSession) -> None:
        """Test POST /api/graph/search/hybrid endpoint."""
        metrics = self.results.endpoints["hybrid_search"]

        query = random.choice(SEARCH_QUERIES)
        payload = {
            "query": query,
            "top_k": random.randint(5, 15),
            "alpha": 0.3,
            "threshold": 0.1,
            "search_decisions": True,
            "search_entities": random.choice([True, False]),
        }

        url = f"{self.base_url}/api/graph/search/hybrid"

        start = time.perf_counter()
        try:
            async with session.post(url, json=payload) as response:
                latency = (time.perf_counter() - start) * 1000
                metrics.latencies.append(latency)

                if response.status == 200:
                    body = await response.json()
                    if isinstance(body, list):
                        metrics.successes += 1
                    else:
                        metrics.failures += 1
                        metrics.errors.append("Invalid response format")
                else:
                    metrics.failures += 1
                    metrics.errors.append(f"Status {response.status}")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            metrics.latencies.append(latency)
            metrics.failures += 1
            metrics.errors.append(str(e))

    async def test_dashboard_stats(self, session: aiohttp.ClientSession) -> None:
        """Test GET /api/dashboard/stats endpoint."""
        metrics = self.results.endpoints["dashboard_stats"]

        url = f"{self.base_url}/api/dashboard/stats"

        start = time.perf_counter()
        try:
            async with session.get(url) as response:
                latency = (time.perf_counter() - start) * 1000
                metrics.latencies.append(latency)

                if response.status == 200:
                    body = await response.json()
                    if "total_decisions" in body and "total_entities" in body:
                        metrics.successes += 1
                    else:
                        metrics.failures += 1
                        metrics.errors.append("Missing expected fields")
                else:
                    metrics.failures += 1
                    metrics.errors.append(f"Status {response.status}")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            metrics.latencies.append(latency)
            metrics.failures += 1
            metrics.errors.append(str(e))

    async def worker(self, session: aiohttp.ClientSession, worker_id: int) -> None:
        """Worker that continuously makes requests."""
        # Weighted endpoint selection
        endpoints = [
            (self.test_decisions, 0.30),  # 30%
            (self.test_graph, 0.25),  # 25%
            (self.test_hybrid_search, 0.20),  # 20%
            (self.test_dashboard_stats, 0.25),  # 25%
        ]

        while True:
            rand = random.random()
            cumulative = 0.0

            for test_func, weight in endpoints:
                cumulative += weight
                if rand < cumulative:
                    await test_func(session)
                    break

            # Sleep to maintain target RPS
            await asyncio.sleep(1.0 / self.target_rps * 10 + random.uniform(0, 0.1))

    async def run(self) -> LoadTestResults:
        """Run the load test."""
        print("=" * 60)
        print("Continuum API Load Test")
        print("=" * 60)
        print(f"Target: {self.target_rps} RPS with p99 < 500ms")
        print(f"Duration: {self.duration_seconds}s (+ {self.ramp_up_seconds}s ramp-up)")
        print(f"Base URL: {self.base_url}")
        print("=" * 60)

        connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        ) as session:
            # Health check
            print("\nChecking API health...", end=" ")
            if not await self.check_health(session):
                print("FAILED")
                print("API is not healthy. Please ensure the API is running.")
                sys.exit(1)
            print("OK")

            # Start workers
            print(f"\nStarting {self.target_rps} concurrent workers...")
            self.results.start_time = datetime.now()

            workers = []
            for i in range(self.target_rps):
                workers.append(asyncio.create_task(self.worker(session, i)))

            # Run for the specified duration
            try:
                # Progress reporting
                start = time.time()
                while time.time() - start < self.duration_seconds:
                    elapsed = time.time() - start
                    requests = self.results.total_requests
                    rps = requests / elapsed if elapsed > 0 else 0

                    print(
                        f"\rProgress: {elapsed:.0f}s/{self.duration_seconds}s | "
                        f"Requests: {requests} | "
                        f"RPS: {rps:.1f} | "
                        f"Success: {self.results.overall_success_rate:.1f}%",
                        end="",
                    )
                    await asyncio.sleep(1)

                print()  # Newline after progress

            finally:
                # Cancel all workers
                for worker in workers:
                    worker.cancel()

                # Wait for cancellation
                await asyncio.gather(*workers, return_exceptions=True)

        self.results.end_time = datetime.now()
        return self.results

    def print_results(self) -> None:
        """Print formatted test results."""
        results = self.results

        print("\n" + "=" * 60)
        print("LOAD TEST RESULTS")
        print("=" * 60)

        print(f"\nDuration: {results.duration_seconds:.1f}s")
        print(f"Total Requests: {results.total_requests}")
        print(f"Actual RPS: {results.actual_rps:.1f}")
        print(f"Target RPS: {results.target_rps}")
        print(f"Overall Success Rate: {results.overall_success_rate:.2f}%")

        print("\n" + "-" * 60)
        print("LATENCY PERCENTILES (ms)")
        print("-" * 60)
        print(
            f"{'Endpoint':<20} {'Min':>8} {'Avg':>8} {'P50':>8} {'P95':>8} {'P99':>8} {'Max':>8}"
        )
        print("-" * 60)

        for name, metrics in results.endpoints.items():
            print(
                f"{name:<20} "
                f"{metrics.min:>8.1f} "
                f"{metrics.avg:>8.1f} "
                f"{metrics.p50:>8.1f} "
                f"{metrics.p95:>8.1f} "
                f"{metrics.p99:>8.1f} "
                f"{metrics.max:>8.1f}"
            )

        print("-" * 60)
        all_latencies = results.all_latencies
        if all_latencies:
            print(
                f"{'OVERALL':<20} "
                f"{min(all_latencies):>8.1f} "
                f"{statistics.mean(all_latencies):>8.1f} "
                f"{sorted(all_latencies)[len(all_latencies) // 2]:>8.1f} "
                f"{sorted(all_latencies)[int(len(all_latencies) * 0.95)]:>8.1f} "
                f"{results.overall_p99:>8.1f} "
                f"{max(all_latencies):>8.1f}"
            )

        print("\n" + "-" * 60)
        print("ENDPOINT SUMMARY")
        print("-" * 60)
        print(
            f"{'Endpoint':<20} {'Requests':>10} {'Success':>10} {'Failures':>10} {'Rate':>10}"
        )
        print("-" * 60)

        for name, metrics in results.endpoints.items():
            print(
                f"{name:<20} "
                f"{metrics.total_requests:>10} "
                f"{metrics.successes:>10} "
                f"{metrics.failures:>10} "
                f"{metrics.success_rate:>9.1f}%"
            )

        # Test pass/fail
        print("\n" + "=" * 60)
        if results.passed():
            print("TEST RESULT: PASSED")
            print(f"  p99 latency ({results.overall_p99:.1f}ms) < 500ms target")
            print(f"  Success rate ({results.overall_success_rate:.1f}%) > 99%")
        else:
            print("TEST RESULT: FAILED")
            if results.overall_p99 >= 500:
                print(
                    f"  FAIL: p99 latency ({results.overall_p99:.1f}ms) >= 500ms target"
                )
            if results.overall_success_rate <= 99.0:
                print(
                    f"  FAIL: Success rate ({results.overall_success_rate:.1f}%) <= 99%"
                )
        print("=" * 60)

    def save_results(self, filename: str = "load_test_results.json") -> None:
        """Save results to JSON file."""
        results = self.results

        data = {
            "start_time": results.start_time.isoformat(),
            "end_time": results.end_time.isoformat() if results.end_time else None,
            "duration_seconds": results.duration_seconds,
            "target_rps": results.target_rps,
            "actual_rps": results.actual_rps,
            "total_requests": results.total_requests,
            "overall_success_rate": results.overall_success_rate,
            "overall_p99": results.overall_p99,
            "passed": results.passed(),
            "endpoints": {},
        }

        for name, metrics in results.endpoints.items():
            data["endpoints"][name] = {
                "total_requests": metrics.total_requests,
                "successes": metrics.successes,
                "failures": metrics.failures,
                "success_rate": metrics.success_rate,
                "latency_min": metrics.min,
                "latency_avg": metrics.avg,
                "latency_p50": metrics.p50,
                "latency_p95": metrics.p95,
                "latency_p99": metrics.p99,
                "latency_max": metrics.max,
            }

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

        print(f"\nResults saved to: {filename}")


def main():
    if aiohttp is None:
        print("Error: aiohttp is required. Install with: pip install aiohttp")
        sys.exit(1)
    parser = argparse.ArgumentParser(description="Continuum API Load Test")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--rps",
        type=int,
        default=50,
        help="Target requests per second (default: 50)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Test duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--ramp-up",
        type=int,
        default=10,
        help="Ramp-up time in seconds (default: 10)",
    )
    parser.add_argument(
        "--output",
        default="load_test_results.json",
        help="Output file for results (default: load_test_results.json)",
    )

    args = parser.parse_args()

    tester = LoadTester(
        base_url=args.base_url,
        target_rps=args.rps,
        duration_seconds=args.duration,
        ramp_up_seconds=args.ramp_up,
    )

    try:
        asyncio.run(tester.run())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        tester.results.end_time = datetime.now()

    tester.print_results()
    tester.save_results(args.output)

    # Exit with error code if test failed
    sys.exit(0 if tester.results.passed() else 1)


if __name__ == "__main__":
    main()
