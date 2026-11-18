#!/usr/bin/python3
"""
vending_usage.py - Vending Usage Report (last 24 months)

Queries the vendinglog table in log.db to produce a monthly breakdown of:
  - Number of vending transactions (purchases)
  - Total $ charged
  - Number of unique members using vending
  - Number of balance additions and total $ added
  - Top products by purchase count

Output: HTML table via the HTML: prefix convention.
"""

import sqlite3
import sys
import os
from datetime import datetime
from collections import defaultdict
from html import escape

LOOKBACK_MONTHS = 24
LOG_DB = "../../../log.db"
MAKEIT_DB = "../../../makeit.db"


def get_month_range(months_back):
    """Generate list of YYYY-MM strings from months_back ago to now."""
    now = datetime.now()
    result = []
    y, m = now.year, now.month
    for _ in range(months_back):
        m -= 1
        if m < 1:
            m = 12
            y -= 1
    # Now y,m is the start month
    start_y, start_m = y, m
    while (y, m) <= (now.year, now.month):
        result.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result


def main():
    try:
        conn = sqlite3.connect(LOG_DB)
        conn.execute(f'ATTACH DATABASE "{MAKEIT_DB}" AS makeit')
        cursor = conn.cursor()
    except Exception as e:
        print(f"HTML:<div style='padding:20px; color:red;'>Database error: {escape(str(e))}</div>")
        sys.exit(1)

    months = get_month_range(LOOKBACK_MONTHS)

    # Monthly purchase stats from vendinglog
    # purchaseAmount > 0 means it's a purchase (not a balance add)
    cursor.execute("""
        SELECT
            strftime('%Y-%m', time_logged) AS ym,
            COUNT(*) AS txn_count,
            SUM(totalCharge) AS total_charged,
            COUNT(DISTINCT member_id) AS unique_members
        FROM vendinglog
        WHERE purchaseAmount > 0
          AND strftime('%Y-%m', time_logged) >= ?
        GROUP BY ym
        ORDER BY ym
    """, (months[0],))

    purchase_data = {}
    for row in cursor.fetchall():
        ym, txn_count, total_charged, unique_members = row
        purchase_data[ym] = {
            'txn_count': txn_count or 0,
            'total_charged': (total_charged or 0) / 100.0,  # stored in cents
            'unique_members': unique_members or 0
        }

    # Monthly balance additions
    cursor.execute("""
        SELECT
            strftime('%Y-%m', time_logged) AS ym,
            COUNT(*) AS add_count,
            SUM(addAmount) AS total_added
        FROM vendinglog
        WHERE addAmount > 0
          AND strftime('%Y-%m', time_logged) >= ?
        GROUP BY ym
        ORDER BY ym
    """, (months[0],))

    balance_data = {}
    for row in cursor.fetchall():
        ym, add_count, total_added = row
        balance_data[ym] = {
            'add_count': add_count or 0,
            'total_added': (total_added or 0) / 100.0
        }

    since_date_str = os.environ.get('REPORT_SINCE', '')
    if since_date_str:
        bottom_tables_since = since_date_str
    else:
        # Default to 3 months ago for the bottom tables
        bottom_tables_since = get_month_range(3)[0] + "-01"

    # Top products (all time within window)
    cursor.execute("""
        SELECT
            product,
            COUNT(*) AS cnt,
            SUM(totalCharge) AS total
        FROM vendinglog
        WHERE purchaseAmount > 0
          AND product IS NOT NULL
          AND product != ''
          AND strftime('%Y-%m-%d', time_logged) >= ?
        GROUP BY product
        ORDER BY cnt DESC
        LIMIT 15
    """, (bottom_tables_since,))
    top_products = cursor.fetchall()

    # Top members by spend
    cursor.execute("""
        SELECT
            m.member,
            COUNT(*) AS cnt,
            SUM(v.totalCharge) AS total
        FROM vendinglog v
        LEFT JOIN makeit.members m ON v.member_id = m.id
        WHERE v.purchaseAmount > 0
          AND strftime('%Y-%m-%d', v.time_logged) >= ?
        GROUP BY v.member_id
        ORDER BY total DESC
        LIMIT 15
    """, (bottom_tables_since,))
    top_members = cursor.fetchall()

    conn.close()

    # Build HTML output
    html = "HTML:"
    html += "<div style='font-family: Arial, sans-serif; padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>"
    html += "<h2 style='color: #333; margin-top: 0;'>Vending Usage Report</h2>"
    html += f"<p style='color: #666; margin-bottom: 20px;'>Last {LOOKBACK_MONTHS} months ({months[0]} to {months[-1]})</p>"

    # --- Monthly Summary Table ---
    html += "<h3 style='border-bottom: 1px solid #ccc; padding-bottom: 5px;'>Monthly Summary</h3>"
    html += "<table style='border-collapse: collapse; width: 100%; font-size: 14px; margin-bottom: 30px;'>"
    html += "<thead><tr style='background-color: #0d6efd; color: white;'>"
    html += "<th style='padding: 8px 12px; text-align: left;'>Month</th>"
    html += "<th style='padding: 8px 12px; text-align: right;'>Purchases</th>"
    html += "<th style='padding: 8px 12px; text-align: right;'>$ Charged</th>"
    html += "<th style='padding: 8px 12px; text-align: right;'>Unique Users</th>"
    html += "<th style='padding: 8px 12px; text-align: right;'>Balance Adds</th>"
    html += "<th style='padding: 8px 12px; text-align: right;'>$ Added</th>"
    html += "</tr></thead><tbody>"

    grand_txn = 0
    grand_charged = 0.0
    grand_adds = 0
    grand_added = 0.0

    for i, ym in enumerate(months):
        p = purchase_data.get(ym, {'txn_count': 0, 'total_charged': 0.0, 'unique_members': 0})
        b = balance_data.get(ym, {'add_count': 0, 'total_added': 0.0})
        bg = "#f8f9fa" if i % 2 == 0 else "#ffffff"

        grand_txn += p['txn_count']
        grand_charged += p['total_charged']
        grand_adds += b['add_count']
        grand_added += b['total_added']

        html += f"<tr style='background-color: {bg};'>"
        html += f"<td style='padding: 6px 12px;'>{ym}</td>"
        html += f"<td style='padding: 6px 12px; text-align: right;'>{p['txn_count']}</td>"
        html += f"<td style='padding: 6px 12px; text-align: right;'>${p['total_charged']:.2f}</td>"
        html += f"<td style='padding: 6px 12px; text-align: right;'>{p['unique_members']}</td>"
        html += f"<td style='padding: 6px 12px; text-align: right;'>{b['add_count']}</td>"
        html += f"<td style='padding: 6px 12px; text-align: right;'>${b['total_added']:.2f}</td>"
        html += "</tr>"

    # Totals row
    html += "<tr style='background-color: #e9ecef; font-weight: bold; border-top: 2px solid #0d6efd;'>"
    html += "<td style='padding: 6px 12px;'>TOTAL</td>"
    html += f"<td style='padding: 6px 12px; text-align: right;'>{grand_txn}</td>"
    html += f"<td style='padding: 6px 12px; text-align: right;'>${grand_charged:.2f}</td>"
    html += "<td style='padding: 6px 12px; text-align: right;'></td>"
    html += f"<td style='padding: 6px 12px; text-align: right;'>{grand_adds}</td>"
    html += f"<td style='padding: 6px 12px; text-align: right;'>${grand_added:.2f}</td>"
    html += "</tr>"

    html += "</tbody></table>"

    # --- Top Products Table ---
    if top_products:
        html += "<div style='display: flex; flex-wrap: wrap; gap: 40px;'>"
        html += "<div>"
        html += "<h3 style='border-bottom: 1px solid #ccc; padding-bottom: 5px;'>Top Products</h3>"
        html += f"<p style='color: #888; font-size: 12px; margin-top: -5px;'>Since {bottom_tables_since}</p>"
        html += "<table style='border-collapse: collapse; font-size: 14px; margin-bottom: 30px;'>"
        html += "<thead><tr style='background-color: #198754; color: white;'>"
        html += "<th style='padding: 8px 12px; text-align: left;'>Product</th>"
        html += "<th style='padding: 8px 12px; text-align: right;'>Count</th>"
        html += "<th style='padding: 8px 12px; text-align: right;'>$ Total</th>"
        html += "</tr></thead><tbody>"
        for i, (product, cnt, total) in enumerate(top_products):
            bg = "#f8f9fa" if i % 2 == 0 else "#ffffff"
            total_dollars = (total or 0) / 100.0
            html += f"<tr style='background-color: {bg};'>"
            html += f"<td style='padding: 6px 12px;'>{escape(str(product))}</td>"
            html += f"<td style='padding: 6px 12px; text-align: right;'>{cnt}</td>"
            html += f"<td style='padding: 6px 12px; text-align: right;'>${total_dollars:.2f}</td>"
            html += "</tr>"
        html += "</tbody></table>"
        html += "</div>"

        # --- Top Members Table ---
        if top_members:
            html += "<div>"
            html += "<h3 style='border-bottom: 1px solid #ccc; padding-bottom: 5px;'>Top Members by Spend</h3>"
            html += f"<p style='color: #888; font-size: 12px; margin-top: -5px;'>Since {bottom_tables_since}</p>"
            html += "<table style='border-collapse: collapse; font-size: 14px; margin-bottom: 30px;'>"
            html += "<thead><tr style='background-color: #6f42c1; color: white;'>"
            html += "<th style='padding: 8px 12px; text-align: left;'>Member</th>"
            html += "<th style='padding: 8px 12px; text-align: right;'>Purchases</th>"
            html += "<th style='padding: 8px 12px; text-align: right;'>$ Total</th>"
            html += "</tr></thead><tbody>"
            for i, (member, cnt, total) in enumerate(top_members):
                bg = "#f8f9fa" if i % 2 == 0 else "#ffffff"
                total_dollars = (total or 0) / 100.0
                member_name = escape(str(member)) if member else "(unknown)"
                html += f"<tr style='background-color: {bg};'>"
                html += f"<td style='padding: 6px 12px;'>{member_name}</td>"
                html += f"<td style='padding: 6px 12px; text-align: right;'>{cnt}</td>"
                html += f"<td style='padding: 6px 12px; text-align: right;'>${total_dollars:.2f}</td>"
                html += "</tr>"
            html += "</tbody></table>"
            html += "</div>"

        html += "</div>"  # end flex container

    html += "</div>"
    print(html)
    sys.exit(0)


if __name__ == "__main__":
    main()
