"""
Passparto Daily Report — collects data, generates insight, sends Klaviyo event.

Usage:
    python src/main.py           # Full run (for cron)
    python src/main.py --dry-run # Collect + insight, skip sending event
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from data_collector import collect_all
from insights_generator import generate_insight
from klaviyo_event import send_daily_report_event


def main():
    parser = argparse.ArgumentParser(description="Passparto Daily Report")
    parser.add_argument("--dry-run", action="store_true", help="Skip sending event")
    args = parser.parse_args()

    print("=" * 50)
    print("  Passparto Daily Report")
    print("=" * 50)

    try:
        print("\n[1/3] Collecting data...")
        data = collect_all()

        print("\n[2/3] Generating insight...")
        insight = generate_insight(data)
        print(f"  Insight: {insight}")

        if args.dry_run:
            print("\n  --dry-run: event NOT sent.")
            return

        print("\n[3/3] Sending event to Klaviyo...")
        success = send_daily_report_event(data, insight)

        if success:
            print("\n  Done — event sent.")
        else:
            print("\n  Event failed.")
            sys.exit(1)

    except Exception as e:
        print(f"\n  CRASH: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
