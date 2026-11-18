#!/usr/bin/env python3
"""
Member Retention & Growth Report

Queries Stripe subscription data to produce a monthly breakdown of:
  - Active member count
  - New members (subscriptions started)
  - Lost members (subscriptions canceled/ended)
  - Net change
  - Monthly retention rate

Output: Human-readable text table + CSV block for easy spreadsheet import.

Follows the same patterns as membercount.py and membergraph.py.
"""

import stripe
from datetime import datetime, timedelta
from collections import defaultdict
import sys

# Valid membership plan IDs (same as other reports)
MEMBERSHIPS = ['hobbyist', 'pro', 'produo']

# Exempt coupon names — these are free memberships, excluded from counts
EXEMPT = [
    '100PERCENTOFF',
    'NonProfit -Free 1yr Memberships',
    '100% off in perpetuity- Do NOT use'
]

# Default lookback in months
LOOKBACK_MONTHS = 24


def month_key(ts):
    """Convert a unix timestamp to a 'YYYY-MM' string."""
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m")


def month_range(start_ym, end_ym):
    """Generate all YYYY-MM strings from start_ym to end_ym inclusive."""
    sy, sm = map(int, start_ym.split("-"))
    ey, em = map(int, end_ym.split("-"))
    months = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def get_coupon_name(s):
    """Extract coupon name from a Stripe subscription object."""
    try:
        discount = s.get('discount')
        if discount and discount.get('coupon'):
            coupon = discount['coupon']
            name = coupon.get('name')
            if name and name.strip():
                return name
            return coupon.get('id', 'Unknown Coupon')
    except (TypeError, KeyError):
        pass
    return None


def get_member_count(s):
    """Return how many members a subscription represents (produo=2)."""
    plan_id = s.get('plan', {}).get('id', '')
    return 2 if plan_id == 'produo' else 1


def main():
    try:
        stripe.api_key = open("stripenamefix.key").readline().strip()
    except FileNotFoundError:
        print("Error: stripenamefix.key not found. Run from authlibs/reports/reports/", file=sys.stderr)
        sys.exit(1)

    stripe.api_version = '2020-08-27'

    now = datetime.now()
    since = datetime(now.year, now.month, 1) - timedelta(days=LOOKBACK_MONTHS * 31)
    since_ts = int(since.timestamp())

    current_ym = now.strftime("%Y-%m")
    start_ym = since.strftime("%Y-%m")
    all_months = month_range(start_ym, current_ym)

    # Per-month accumulators
    active_in_month = defaultdict(int)   # total active during this month
    new_in_month = defaultdict(int)      # started in this month
    lost_in_month = defaultdict(int)     # canceled/ended in this month

    processed = set()
    sub_count = 0

    # Query Stripe: all subs that are currently active OR were canceled within our window
    query = f'canceled_at>{since_ts} or status:"active"'

    for s in stripe.Subscription.search(query=query).auto_paging_iter():
        if s['id'] in processed:
            continue
        processed.add(s['id'])

        plan = s.get('plan')
        if plan is None or plan.get('id') not in MEMBERSHIPS:
            continue

        # Check for exempt coupons
        coupon = get_coupon_name(s)
        if coupon in EXEMPT:
            continue

        mcount = get_member_count(s)
        sub_count += 1

        # Determine subscription lifespan
        start_ts = s.get('start_date')
        if start_ts is None:
            continue

        end_ts = s.get('canceled_at') or s.get('ended_at')

        sub_start_ym = month_key(start_ts)
        sub_end_ym = month_key(end_ts) if end_ts else None

        # Mark this subscription as active in each month it was alive
        for ym in all_months:
            # Sub is active in this month if it started on or before this month
            # and hasn't ended before this month
            if sub_start_ym <= ym:
                if sub_end_ym is None or sub_end_ym >= ym:
                    active_in_month[ym] += mcount

        # Mark new join
        if sub_start_ym in active_in_month or sub_start_ym in [m for m in all_months]:
            new_in_month[sub_start_ym] += mcount

        # Mark loss
        if sub_end_ym and sub_end_ym in [m for m in all_months]:
            lost_in_month[sub_end_ym] += mcount

    # Print human-readable report
    print(f"Member Retention & Growth Report ({LOOKBACK_MONTHS} months)")
    print(f"Subscriptions processed: {sub_count}")
    print("=" * 62)
    print(f"{'Month':>10s}  {'Active':>7s}  {'New':>5s}  {'Lost':>5s}  {'Net':>5s}  {'Retention%':>10s}")
    print("-" * 62)

    retention_values = []

    for i, ym in enumerate(all_months):
        active = active_in_month.get(ym, 0)
        new = new_in_month.get(ym, 0)
        lost = lost_in_month.get(ym, 0)
        net = new - lost

        # Retention = (prev_active - lost) / prev_active * 100
        if i > 0:
            prev_active = active_in_month.get(all_months[i - 1], 0)
            if prev_active > 0:
                retention = (prev_active - lost) / prev_active * 100.0
                retention_str = f"{retention:>9.1f}%"
                retention_values.append(retention)
            else:
                retention_str = "       N/A"
        else:
            retention_str = "       N/A"

        net_str = f"+{net}" if net >= 0 else str(net)
        print(f"{ym:>10s}  {active:>7d}  {new:>5d}  {lost:>5d}  {net_str:>5s}  {retention_str}")

    print("=" * 62)

    if retention_values:
        avg_retention = sum(retention_values) / len(retention_values)
        print(f"Average Monthly Retention: {avg_retention:.1f}%")
    print()

    # Print CSV block
    print("--- CSV DATA ---")
    print("Month,Active,New,Lost,Net,Retention%")
    for i, ym in enumerate(all_months):
        active = active_in_month.get(ym, 0)
        new = new_in_month.get(ym, 0)
        lost = lost_in_month.get(ym, 0)
        net = new - lost

        if i > 0:
            prev_active = active_in_month.get(all_months[i - 1], 0)
            if prev_active > 0:
                retention = (prev_active - lost) / prev_active * 100.0
                retention_str = f"{retention:.1f}"
            else:
                retention_str = "N/A"
        else:
            retention_str = "N/A"

        print(f"{ym},{active},{new},{lost},{net},{retention_str}")

    sys.exit(0)


if __name__ == "__main__":
    main()
