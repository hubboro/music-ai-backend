import argparse
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supabase_utils import save_app_heartbeat  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="Write a daily Butterfly heartbeat row to Supabase.")
    parser.add_argument("--source", default=os.getenv("HEARTBEAT_SOURCE", "render-cron"))
    parser.add_argument("--no-delay", action="store_true", help="Skip the random startup delay.")
    return parser.parse_args()


def maybe_sleep(no_delay):
    if no_delay:
        return 0

    max_delay = int(os.getenv("HEARTBEAT_MAX_RANDOM_DELAY_SECONDS", "600"))
    if max_delay <= 0:
        return 0

    delay = random.randint(0, max_delay)
    if delay:
        print(f"Sleeping {delay}s before heartbeat")
        time.sleep(delay)
    return delay


def main():
    args = parse_args()
    maybe_sleep(args.no_delay)
    heartbeat = save_app_heartbeat(source=args.source)
    print(
        "Supabase heartbeat saved:",
        {
            "run_date": heartbeat.get("run_date"),
            "source": heartbeat.get("source"),
            "status": heartbeat.get("status"),
            "metrics": heartbeat.get("metrics", {}),
        },
    )


if __name__ == "__main__":
    main()
