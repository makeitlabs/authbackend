#!/usr/bin/python3
"""
door_usage.py - Door / Facility Usage Report (last 24 months)

Queries the log table in log.db for "Allowed Entry" events (event_type 1025)
to produce:
  - Monthly unique members through the door
  - Top members by visit count
  - Top members by unique days visited per month (avg)

Output: HTML table via the HTML: prefix convention.
"""

import sqlite3
import sys
import os
from datetime import datetime
from html import escape

LOOKBACK_MONTHS = 24
LOG_DB = "../../../log.db"
MAKEIT_DB = "../../../makeit.db"
EVENT_ENTRY_ALLOWED = 1025


def get_month_range(months_back):
    """Generate list of YYYY-MM strings from months_back ago to now."""
    now = datetime.now()
    y, m = now.year, now.month
    for _ in range(months_back):
        m -= 1
        if m < 1:
            m = 12
            y -= 1
    result = []
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

    # Monthly unique members and total entries
    cursor.execute("""
        SELECT
            strftime('%Y-%m', time_logged) AS ym,
            COUNT(*) AS total_entries,
            COUNT(DISTINCT member_id) AS unique_members
        FROM log
        WHERE event_type = ?
          AND member_id > 0
          AND strftime('%Y-%m', time_logged) >= ?
        GROUP BY ym
        ORDER BY ym
    """, (EVENT_ENTRY_ALLOWED, months[0]))

    monthly_data = {}
    for row in cursor.fetchall():
        ym, total_entries, unique_members = row
        monthly_data[ym] = {
            'total_entries': total_entries or 0,
            'unique_members': unique_members or 0
        }

    since_date_str = os.environ.get('REPORT_SINCE', '')
    if since_date_str:
        bottom_tables_since = since_date_str
    else:
        # Default to 3 months ago for the bottom tables
        bottom_tables_since = get_month_range(3)[0] + "-01"

    # Top 25 members by total entries in the window
    cursor.execute("""
        SELECT
            m.member,
            COUNT(*) AS cnt,
            COUNT(DISTINCT strftime('%Y-%m-%d', l.time_logged)) AS unique_days
        FROM log l
        LEFT JOIN makeit.members m ON l.member_id = m.id
        WHERE l.event_type = ?
          AND l.member_id > 0
          AND strftime('%Y-%m-%d', l.time_logged) >= ?
        GROUP BY l.member_id
        ORDER BY cnt DESC
        LIMIT 25
    """, (EVENT_ENTRY_ALLOWED, bottom_tables_since))
    top_members = cursor.fetchall()

    # Per-member unique days per month (top 25 by avg unique days/month)
    cursor.execute("""
        SELECT
            m.member,
            COUNT(DISTINCT strftime('%Y-%m-%d', l.time_logged)) AS total_unique_days,
            COUNT(DISTINCT strftime('%Y-%m', l.time_logged)) AS active_months,
            ROUND(CAST(COUNT(DISTINCT strftime('%Y-%m-%d', l.time_logged)) AS FLOAT) /
                  COUNT(DISTINCT strftime('%Y-%m', l.time_logged)), 1) AS avg_days_per_month
        FROM log l
        LEFT JOIN makeit.members m ON l.member_id = m.id
        WHERE l.event_type = ?
          AND l.member_id > 0
          AND strftime('%Y-%m-%d', l.time_logged) >= ?
        GROUP BY l.member_id
        HAVING active_months >= 3
        ORDER BY avg_days_per_month DESC
        LIMIT 25
    """, (EVENT_ENTRY_ALLOWED, bottom_tables_since))
    top_by_days = cursor.fetchall()

    conn.close()

    # Build HTML output
    html = "HTML:"
    html += "<div style='font-family: Arial, sans-serif; padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>"
    html += "<h2 style='color: #333; margin-top: 0;'>Door / Facility Usage Report</h2>"
    html += f"<p style='color: #666; margin-bottom: 20px;'>Last {LOOKBACK_MONTHS} months ({months[0]} to {months[-1]})</p>"

    # --- Monthly Summary Table ---
    html += "<h3 style='border-bottom: 1px solid #ccc; padding-bottom: 5px;'>Monthly Door Usage</h3>"
    html += "<table style='border-collapse: collapse; width: 100%; max-width: 600px; font-size: 14px; margin-bottom: 30px;'>"
    html += "<thead><tr style='background-color: #0d6efd; color: white;'>"
    html += "<th style='padding: 8px 12px; text-align: left;'>Month</th>"
    html += "<th style='padding: 8px 12px; text-align: right;'>Total Entries</th>"
    html += "<th style='padding: 8px 12px; text-align: right;'>Unique Members</th>"
    html += "<th style='padding: 8px 12px; text-align: right;'>Avg Entries/Member</th>"
    html += "</tr></thead><tbody>"

    grand_entries = 0
    grand_unique = 0

    for i, ym in enumerate(months):
        d = monthly_data.get(ym, {'total_entries': 0, 'unique_members': 0})
        bg = "#f8f9fa" if i % 2 == 0 else "#ffffff"

        grand_entries += d['total_entries']
        grand_unique += d['unique_members']

        avg = d['total_entries'] / d['unique_members'] if d['unique_members'] > 0 else 0

        html += f"<tr style='background-color: {bg};'>"
        html += f"<td style='padding: 6px 12px;'>{ym}</td>"
        html += f"<td style='padding: 6px 12px; text-align: right;'>{d['total_entries']}</td>"
        html += f"<td style='padding: 6px 12px; text-align: right;'>{d['unique_members']}</td>"
        html += f"<td style='padding: 6px 12px; text-align: right;'>{avg:.1f}</td>"
        html += "</tr>"

    html += "</tbody></table>"

    # --- Side by side tables ---
    html += "<div style='display: flex; flex-wrap: wrap; gap: 40px;'>"

    # --- Top Members by Total Visits ---
    if top_members:
        html += "<div>"
        html += f"<h3 style='border-bottom: 1px solid #ccc; padding-bottom: 5px;'>Top 25 Members by Visits</h3>"
        html += f"<p style='color: #888; font-size: 12px; margin-top: -5px;'>Since {bottom_tables_since}</p>"
        html += "<table style='border-collapse: collapse; font-size: 14px; margin-bottom: 30px;'>"
        html += "<thead><tr style='background-color: #198754; color: white;'>"
        html += "<th style='padding: 8px 12px; text-align: left;'>Member</th>"
        html += "<th style='padding: 8px 12px; text-align: right;'>Total Entries</th>"
        html += "<th style='padding: 8px 12px; text-align: right;'>Unique Days</th>"
        html += "</tr></thead><tbody>"
        for i, (member, cnt, unique_days) in enumerate(top_members):
            bg = "#f8f9fa" if i % 2 == 0 else "#ffffff"
            member_name = escape(str(member)) if member else "(unknown)"
            html += f"<tr style='background-color: {bg};'>"
            html += f"<td style='padding: 6px 12px;'>{member_name}</td>"
            html += f"<td style='padding: 6px 12px; text-align: right;'>{cnt}</td>"
            html += f"<td style='padding: 6px 12px; text-align: right;'>{unique_days}</td>"
            html += "</tr>"
        html += "</tbody></table>"
        html += "</div>"

    # --- Top Members by Avg Days/Month ---
    if top_by_days:
        html += "<div>"
        html += "<h3 style='border-bottom: 1px solid #ccc; padding-bottom: 5px;'>Most Consistent Members (Avg Days/Month)</h3>"
        html += f"<p style='color: #888; font-size: 12px; margin-top: -5px;'>Since {bottom_tables_since}. Active at least 3 months.</p>"
        html += "<table style='border-collapse: collapse; font-size: 14px; margin-bottom: 30px;'>"
        html += "<thead><tr style='background-color: #6f42c1; color: white;'>"
        html += "<th style='padding: 8px 12px; text-align: left;'>Member</th>"
        html += "<th style='padding: 8px 12px; text-align: right;'>Total Days</th>"
        html += "<th style='padding: 8px 12px; text-align: right;'>Active Months</th>"
        html += "<th style='padding: 8px 12px; text-align: right;'>Avg Days/Mo</th>"
        html += "</tr></thead><tbody>"
        for i, (member, total_days, active_months, avg_days) in enumerate(top_by_days):
            bg = "#f8f9fa" if i % 2 == 0 else "#ffffff"
            member_name = escape(str(member)) if member else "(unknown)"
            html += f"<tr style='background-color: {bg};'>"
            html += f"<td style='padding: 6px 12px;'>{member_name}</td>"
            html += f"<td style='padding: 6px 12px; text-align: right;'>{total_days}</td>"
            html += f"<td style='padding: 6px 12px; text-align: right;'>{active_months}</td>"
            html += f"<td style='padding: 6px 12px; text-align: right;'>{avg_days}</td>"
            html += "</tr>"
        html += "</tbody></table>"
        html += "</div>"

    html += "</div>"  # end flex container
    html += "</div>"
    print(html)
    sys.exit(0)


if __name__ == "__main__":
    main()
