#!/usr/bin/env python3
import argparse
import html
import os
import sqlite3
import sys

GROUP_EMAIL = "active@makeitlabs.com"
GROUP_ADMIN_URL = "https://admin.google.com/ac/groups/00sqyw6441b2kli"
DOMAIN_DELEGATION_URL = "https://admin.google.com/ac/owl/domainwidedelegation"
REQUIRED_GROUP_SCOPE = "https://www.googleapis.com/auth/admin.directory.group.member"


def get_active_member_emails(db_path):
    """Query active members and return (emails, email_to_member) deduplicated case-insensitively."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query members with active subscriptions.
    # We check:
    # 1. subscription.expires_date is in the future or within the 14-day grace period
    # 2. or subscription.active is 'true'
    query = """
        SELECT DISTINCT m.email, m.alt_email, m.member, m.firstname, m.lastname
        FROM members m
        JOIN subscriptions s ON s.member_id = m.id
        WHERE (
            (s.expires_date IS NOT NULL AND s.expires_date > datetime('now', '-14 days'))
            OR s.active = 'true'
        )
    """

    try:
        cursor.execute(query)
        rows = cursor.fetchall()
    finally:
        conn.close()

    emails = []
    emails_seen = set()
    email_to_member = {}

    for email, alt_email, username, firstname, lastname in rows:
        full_name = " ".join(p for p in ((firstname or "").strip(), (lastname or "").strip()) if p)
        member_info = {
            "username": (username or "").strip(),
            "name": full_name or (username or "").strip() or "Unknown",
        }
        for addr in (email, alt_email):
            if addr:
                addr_clean = addr.strip()
                addr_key = addr_clean.lower()
                if addr_clean and addr_key not in emails_seen:
                    emails_seen.add(addr_key)
                    emails.append(addr_clean)
                    email_to_member[addr_key] = member_info

    return emails, email_to_member


def print_csv(emails):
    """Print active member emails in Google Groups bulk-upload CSV format."""
    print("Group Email [Required],Member Email,Member Type,Member Role")
    for addr in emails:
        print(f"{GROUP_EMAIL},{addr},USER,MEMBER")


def _esc(val):
    return html.escape(str(val or ""), quote=True)


def render_sync_html(emails, email_to_member, result):
    """Render an HTML summary report of the Google Group sync."""
    added = result["added"]
    already_present = result["already_present"]
    errors = result["errors"]

    parts = [
        "HTML:<div style='font-family: sans-serif; white-space: normal;'>",
        "<h4 style='margin-top:0;'>Google Groups Active Members Sync</h4>",
        (
            f"<p>Synced active member emails (including personal emails) to "
            f"<strong><code>{_esc(GROUP_EMAIL)}</code></strong> for general member announcements.<br>"
            f"Google Admin Group: <a href='{_esc(GROUP_ADMIN_URL)}' target='_blank' rel='noopener noreferrer'>"
            f"{_esc(GROUP_ADMIN_URL)}</a></p>"
        ),
        "<div style='display:flex; gap:12px; flex-wrap:wrap; margin-bottom:16px;'>",
        f"<div style='padding:10px 14px; background:#f8f9fa; border:1px solid #dee2e6; border-radius:6px;'><strong>{len(emails)}</strong> Total Active Emails</div>",
        f"<div style='padding:10px 14px; background:#d1e7dd; border:1px solid #badbcc; border-radius:6px; color:#0f5132;'><strong>{len(added)}</strong> Newly Added</div>",
        f"<div style='padding:10px 14px; background:#e2e3e5; border:1px solid #d3d6d8; border-radius:6px; color:#41464b;'><strong>{len(already_present)}</strong> Already in Group (Skipped)</div>",
        f"<div style='padding:10px 14px; background:{'#f8d7da' if errors else '#f8f9fa'}; border:1px solid {'#f5c2c7' if errors else '#dee2e6'}; border-radius:6px; color:{'#842029' if errors else '#41464b'};'><strong>{len(errors)}</strong> Errored / Invalid (Skipped)</div>",
        "</div>",
    ]

    if errors:
        parts.append(
            "<div style='margin-bottom:16px; padding:12px; background:#fff3cd; border:1px solid #ffecb5; border-radius:6px;'>"
            "<strong>Skipped / Errored Emails</strong> — these were skipped so valid members could still be added. "
            "Please review and fix these member email addresses:"
            "<table class='table table-sm table-bordered' style='margin-top:8px; margin-bottom:0; background:#fff;'>"
            "<thead><tr><th>Email</th><th>Member</th><th>Username</th><th>Error</th></tr></thead><tbody>"
        )
        for item in errors:
            addr = item.get("email", "")
            info = email_to_member.get(addr.lower(), {})
            parts.append(
                f"<tr><td><code>{_esc(addr)}</code></td>"
                f"<td>{_esc(info.get('name', ''))}</td>"
                f"<td>{_esc(info.get('username', ''))}</td>"
                f"<td style='color:#842029;'>{_esc(item.get('error', ''))}</td></tr>"
            )
        parts.append("</tbody></table></div>")

    if added:
        parts.append(
            "<div style='margin-bottom:16px;'>"
            "<strong>Newly Added Emails</strong>"
            "<table class='table table-sm table-bordered' style='margin-top:8px; background:#fff;'>"
            "<thead><tr><th>Email</th><th>Member</th><th>Username</th></tr></thead><tbody>"
        )
        for addr in added:
            info = email_to_member.get(addr.lower(), {})
            parts.append(
                f"<tr><td><code>{_esc(addr)}</code></td>"
                f"<td>{_esc(info.get('name', ''))}</td>"
                f"<td>{_esc(info.get('username', ''))}</td></tr>"
            )
        parts.append("</tbody></table></div>")
    else:
        parts.append("<p><em>No new emails needed to be added — all valid active member emails are already in the group.</em></p>")

    parts.append("</div>")
    return "".join(parts)


def render_error_html(message):
    """Render an HTML error block with setup guidance if applicable."""
    hint = ""
    lower = str(message).lower()
    if "unauthorized_client" in lower or "insufficient" in lower or "scope" in lower or "forbidden" in lower:
        hint = (
            f"<p style='margin-top:8px; margin-bottom:0;'>Make sure Domain-Wide Delegation at "
            f"<a href='{_esc(DOMAIN_DELEGATION_URL)}' target='_blank' rel='noopener noreferrer'>{_esc(DOMAIN_DELEGATION_URL)}</a> "
            f"includes the scope <code>{_esc(REQUIRED_GROUP_SCOPE)}</code>.</p>"
        )
    return (
        "HTML:<div style='font-family: sans-serif; white-space: normal; padding:14px; "
        "background:#f8d7da; border:1px solid #f5c2c7; border-radius:6px; color:#842029;'>"
        f"<strong>Error syncing to <code>{_esc(GROUP_EMAIL)}</code>:</strong> {_esc(message)}"
        f"{hint}"
        f"<p style='margin-top:8px; margin-bottom:0;'>You can still use <strong>Download CSV</strong> or <strong>View CSV</strong> "
        f"and upload manually at <a href='{_esc(GROUP_ADMIN_URL)}' target='_blank' rel='noopener noreferrer'>{_esc(GROUP_ADMIN_URL)}</a>.</p>"
        "</div>"
    )


def main():
    parser = argparse.ArgumentParser(description="Sync active members to Google Group or export CSV")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--csv", action="store_true", help="Output CSV instead of syncing to Google Group")
    group.add_argument("--sync", action="store_true", help="Sync active members directly to Google Group")
    args = parser.parse_args()

    if args.csv:
        mode = "csv"
    elif args.sync:
        mode = "sync"
    else:
        mode = os.environ.get("REPORT_MODE", "sync").strip().lower()
        if mode not in ("sync", "csv"):
            mode = "sync"

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    db_path = os.path.join(repo_root, "makeit.db")

    if not os.path.exists(db_path):
        msg = f"Database file not found at {db_path}"
        if mode == "csv":
            print(f"Error: {msg}", file=sys.stderr)
        else:
            print(render_error_html(msg))
        sys.exit(1)

    try:
        emails, email_to_member = get_active_member_emails(db_path)
    except Exception as e:
        msg = f"Database error: {e}"
        if mode == "csv":
            print(msg, file=sys.stderr)
        else:
            print(render_error_html(msg))
        sys.exit(1)

    if mode == "csv":
        print_csv(emails)
        return

    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    try:
        from authlibs.google_admin import syncGroupMembers
        result = syncGroupMembers(GROUP_EMAIL, emails)
    except Exception as e:
        print(render_error_html(str(e)))
        sys.exit(1)

    print(render_sync_html(emails, email_to_member, result))


if __name__ == "__main__":
    main()
