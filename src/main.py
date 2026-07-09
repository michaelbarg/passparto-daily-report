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
from direct_send import send_direct, RESEND_API_KEY
from cotton_sync_status import fetch_cotton_sync_status


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

        cs_status = fetch_cotton_sync_status()
        data["cs_pending_count"] = cs_status["pending_count"]
        data["cs_restock_count"] = cs_status["restock_count"]
        data["cs_zero_count"] = cs_status["zero_count"]
        data["cs_last_scan_time"] = cs_status["last_scan_time"]
        data["cs_scan_stale"] = cs_status["scan_stale"]

        print("\n[2/3] Generating insight...")
        insight = generate_insight(data)
        print(f"  Insight: {insight}")

        if args.dry_run:
            print("\n  --dry-run: email NOT sent.")
            return

        if RESEND_API_KEY:
            print("\n[3/3] Delivering email directly via Resend (bypassing Klaviyo Flow)...")
            success = send_direct(data, insight)
            if success:
                print("\n  Done — email delivered.")
                return
            print("  [WARN] Resend failed — falling back to Klaviyo event...")

        print("\n[3/3] Sending event to Klaviyo (fallback / no RESEND_API_KEY)...")
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
