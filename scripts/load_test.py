"""Enqueue many notifications to demonstrate >12/s intake (1M/day average)."""

import argparse
import asyncio
import time
import uuid

import httpx


async def run(base: str, api_key: str, n: int, concurrency: int) -> None:
    headers = {"X-API-Key": api_key}
    success = 0
    failed = 0
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=10) as client:
        async def one(i: int) -> None:
            nonlocal success, failed
            body = {
                "idempotency_key": f"load-{uuid.uuid4()}",
                "user_id": "42",
                "channel": "inapp",
                "category": "social",
                "priority": "normal",
                "template_code": "COMMENT",
                "payload": {"user_name": "load", "text": str(i)},
            }
            async with sem:
                try:
                    r = await client.post(f"{base}/v1/notifications", headers=headers, json=body)
                    if r.status_code == 202:
                        success += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1

        t0 = time.perf_counter()
        await asyncio.gather(*[one(i) for i in range(n)])
        elapsed = time.perf_counter() - t0

    print(f"sent={success} failed={failed} elapsed_s={elapsed:.2f} enqueue_rps={success / elapsed:.1f}")
    print("1M/day average is ~12/s; peak target is ~120/s.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--api-key", default="dev-key")
    p.add_argument("-n", type=int, default=2000)
    p.add_argument("--concurrency", type=int, default=100)
    args = p.parse_args()
    asyncio.run(run(args.base, args.api_key, args.n, args.concurrency))
