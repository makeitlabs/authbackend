#!/usr/bin/env python3
"""
fiber_candidates.py - Fiber Laser (xTool) Expedited Authorization Recommendations

Recommends the top 75 active members who are the best candidates for expedited
authorization on the new Fiber laser (xTool Fiber, resource id 49).

Qualifications scored:
- UV Laser (id 47): Very important (same software flow)
- Epilog Laser (id 30): Very important (experience & runtime)
- MOPA Laser (id 29): Important (laser & galvo/fiber proficiency)
- Machine Shop (ids 15, 16, 33, 34, 41, etc.): Supplemental (metalworking familiarity)
- Other Lasers (ids 3, 7, 48): Minor supplemental bonus

Focuses on active members only, and usage over the past year (or REPORT_SINCE).
Output format: HTML table with rich visual styling, metrics, and CSV export.
"""

import sqlite3
import sys
import os
from datetime import datetime, timedelta
from html import escape

# Database location defaults (relative to authlibs/reports/reports/)
DEFAULT_MAKEIT_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../makeit.db'))
DEFAULT_LOG_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../log.db'))

MAKEIT_DB = os.environ.get('MAKEIT_DB', DEFAULT_MAKEIT_DB)
LOG_DB = os.environ.get('LOG_DB', DEFAULT_LOG_DB)

# Event IDs for tool logins
EVENT_TOOL_LOGIN = 3013
EVENT_TOOL_LOGIN_COMBO = 3011

# Fallback resource IDs if resources table lookup is not available
TARGET_FIBER_DEFAULT_ID = 49
UV_DEFAULT_ID = 47
EPILOG_DEFAULT_ID = 30
MOPA_DEFAULT_ID = 29
MACHINESHOP_DEFAULT_IDS = {15, 16, 33, 34, 41, 5, 36, 42}
OTHER_LASER_DEFAULT_IDS = {3, 7, 48}


def format_duration(seconds):
    """Format seconds into readable hours and minutes."""
    if not seconds or seconds <= 0:
        return "0h"
    hours = seconds / 3600.0
    if hours >= 10:
        return f"{hours:.1f}h"
    elif hours >= 1:
        mins = int((seconds % 3600) / 60)
        return f"{int(hours)}h {mins}m" if mins > 0 else f"{int(hours)}h"
    else:
        mins = max(1, int(seconds / 60))
        return f"{mins}m"


def resolve_resources(cursor):
    """Dynamically resolve resource IDs from the database or fall back to defaults."""
    target_fiber_ids = set()
    uv_ids = set()
    epilog_ids = set()
    mopa_ids = set()
    machineshop_ids = set()
    other_laser_ids = set()
    resource_names = {}

    try:
        cursor.execute("SELECT id, name, short FROM resources")
        for rid, name, short in cursor.fetchall():
            name_lower = (name or "").lower()
            short_lower = (short or "").lower()
            resource_names[rid] = short or name or f"Resource {rid}"

            # Fiber laser (Target)
            if rid == TARGET_FIBER_DEFAULT_ID or "laser-fiber" in name_lower or "fiber" in short_lower or "xtool fiber" in short_lower:
                target_fiber_ids.add(rid)

            # UV laser
            elif rid == UV_DEFAULT_ID or "laser-uv" in name_lower or short_lower == "uv":
                uv_ids.add(rid)

            # Epilog laser
            elif rid == EPILOG_DEFAULT_ID or "laser-epilog" in name_lower or "epilog" in short_lower:
                epilog_ids.add(rid)

            # MOPA laser
            elif rid == MOPA_DEFAULT_ID or "laser-mopa" in name_lower or "mopa" in short_lower:
                mopa_ids.add(rid)

            # Machine shop
            elif (rid in MACHINESHOP_DEFAULT_IDS or
                  name_lower.startswith("machineshop") or
                  "bridgeport" in short_lower or
                  "kneemill" in name_lower or
                  "lathe" in name_lower or
                  "tormach" in name_lower or
                  "waterjet" in name_lower or
                  "vert-bandsaw" in name_lower):
                machineshop_ids.add(rid)

            # Other lasers
            elif (rid in OTHER_LASER_DEFAULT_IDS or
                  "laser-rabbit" in name_lower or
                  "laser-fullspectrum" in name_lower or
                  "laser-kern" in name_lower):
                other_laser_ids.add(rid)
    except Exception:
        pass

    # Ensure defaults are present if nothing matched
    if not target_fiber_ids:
        target_fiber_ids.add(TARGET_FIBER_DEFAULT_ID)
    if not uv_ids:
        uv_ids.add(UV_DEFAULT_ID)
    if not epilog_ids:
        epilog_ids.add(EPILOG_DEFAULT_ID)
    if not mopa_ids:
        mopa_ids.add(MOPA_DEFAULT_ID)
    if not machineshop_ids:
        machineshop_ids.update(MACHINESHOP_DEFAULT_IDS)
    if not other_laser_ids:
        other_laser_ids.update(OTHER_LASER_DEFAULT_IDS)

    return target_fiber_ids, uv_ids, epilog_ids, mopa_ids, machineshop_ids, other_laser_ids, resource_names


def get_active_members(cursor):
    """Retrieve all currently active members."""
    # Check if subscriptions table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='subscriptions'")
    has_subscriptions = bool(cursor.fetchone())

    active_members = {}
    try:
        if has_subscriptions:
            query = """
                SELECT DISTINCT m.id, m.member, m.firstname, m.lastname, m.email, m.alt_email
                FROM members m
                LEFT JOIN subscriptions s ON s.member_id = m.id
                WHERE (
                    (m.active IN (1, '1', 'true', 'True', 'Active') OR m.active IS NULL)
                    OR (
                        s.member_id IS NOT NULL AND (
                            s.active IN (1, '1', 'true', 'True')
                            OR (s.expires_date IS NOT NULL AND s.expires_date > datetime('now', '-14 days'))
                        )
                    )
                )
                AND (m.access_enabled IS NULL OR m.access_enabled != 0)
            """
        else:
            query = """
                SELECT DISTINCT m.id, m.member, m.firstname, m.lastname, m.email, m.alt_email
                FROM members m
                WHERE (m.active IN (1, '1', 'true', 'True', 'Active') OR m.active IS NULL)
                  AND (m.access_enabled IS NULL OR m.access_enabled != 0)
            """
        cursor.execute(query)
        for mid, handle, first, last, email, alt_email in cursor.fetchall():
            first = (first or "").strip()
            last = (last or "").strip()
            handle = (handle or "").strip()
            if first and last:
                full_name = f"{first} {last}"
            elif first:
                full_name = first
            elif handle:
                full_name = handle
            else:
                full_name = f"Member #{mid}"

            active_members[mid] = {
                'id': mid,
                'handle': handle,
                'name': full_name,
                'email': email or alt_email or ""
            }
    except Exception as e:
        sys.stderr.write(f"Error querying active members: {e}\n")

    return active_members


def get_authorizations(cursor):
    """Return dictionary of member_id -> dict of authorized resource_id -> details."""
    authorizations = {}
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accessbymember'")
        if not cursor.fetchone():
            return authorizations

        cursor.execute("PRAGMA table_info(accessbymember)")
        cols = {row[1].lower() for row in cursor.fetchall()}

        where_clauses = []
        if 'is_active' in cols:
            where_clauses.append("(is_active = 1 OR is_active IS NULL OR is_active = 'true')")
        elif 'enabled' in cols:
            where_clauses.append("(enabled = 1 OR enabled = '1' OR enabled = 'true')")

        if 'lockout_reason' in cols:
            where_clauses.append("(lockout_reason IS NULL OR lockout_reason = '')")

        if 'level' in cols:
            where_clauses.append("(level IS NULL OR level >= 0)")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        query = f"SELECT member_id, resource_id, level FROM accessbymember {where_sql}"

        cursor.execute(query)
        for mid, rid, level in cursor.fetchall():
            if mid not in authorizations:
                authorizations[mid] = {}
            authorizations[mid][rid] = {
                'level': level
            }
    except Exception as e:
        sys.stderr.write(f"Error querying authorizations: {e}\n")
    return authorizations


def get_usages(cursor, since_date, has_logdb):
    """Aggregate usage (sessions and runtime) per (member_id, resource_id) since since_date."""
    # (member_id, resource_id) -> {'sessions': N, 'runtime_secs': S}
    usage_map = {}

    if not has_logdb:
        return usage_map

    # 1. From usagelog
    try:
        cursor.execute("SELECT name FROM logdb.sqlite_master WHERE type='table' AND name='usagelog'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT member_id, resource_id,
                       COUNT(*) AS session_cnt,
                       SUM(COALESCE(enabledSecs, activeSecs, 0)) AS total_secs
                FROM logdb.usagelog
                WHERE time_logged >= ? AND member_id > 0
                GROUP BY member_id, resource_id
            """, (since_date,))
            for mid, rid, sess_cnt, total_secs in cursor.fetchall():
                key = (mid, rid)
                if key not in usage_map:
                    usage_map[key] = {'sessions': 0, 'runtime_secs': 0}
                usage_map[key]['sessions'] = max(usage_map[key]['sessions'], sess_cnt or 0)
                usage_map[key]['runtime_secs'] = max(usage_map[key]['runtime_secs'], total_secs or 0)
    except Exception as e:
        sys.stderr.write(f"Error reading usagelog: {e}\n")

    # 2. From log table (tool login events)
    try:
        cursor.execute("SELECT name FROM logdb.sqlite_master WHERE type='table' AND name='log'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT member_id, resource_id, COUNT(*) AS login_cnt
                FROM logdb.log
                WHERE event_type IN (?, ?)
                  AND time_logged >= ?
                  AND member_id > 0
                GROUP BY member_id, resource_id
            """, (EVENT_TOOL_LOGIN, EVENT_TOOL_LOGIN_COMBO, since_date))
            for mid, rid, login_cnt in cursor.fetchall():
                key = (mid, rid)
                if key not in usage_map:
                    usage_map[key] = {'sessions': 0, 'runtime_secs': 0}
                # Logins can supplement session count if usagelog wasn't written
                usage_map[key]['sessions'] = max(usage_map[key]['sessions'], login_cnt or 0)
    except Exception as e:
        sys.stderr.write(f"Error reading log: {e}\n")

    return usage_map


def calculate_candidate_scores(active_members, authorizations, usages,
                               target_fiber_ids, uv_ids, epilog_ids, mopa_ids,
                               machineshop_ids, other_laser_ids):
    """
    Compute qualification score and breakdown for each active member.

    Scoring Model (Total potential: 100 points):
    1. UV Laser (35 pts max): Same software flow as xTool Fiber
       - Authorized: 15 pts
       - Sessions (past year): 1.5 pts/session (max 12 pts at 8 sessions)
       - Runtime (past year): 1.0 pt/hr (max 8 pts at 8 hrs)
    2. Epilog Laser (30 pts max): Core laser experience & heavy runtime
       - Authorized: 10 pts
       - Sessions (past year): 1.0 pt/session (max 10 pts at 10 sessions)
       - Runtime (past year): 0.5 pt/hr (max 10 pts at 20 hrs)
    3. MOPA Laser (20 pts max): Galvo/pulsed fiber laser proficiency
       - Authorized: 8 pts
       - Sessions (past year): 1.5 pts/session (max 8 pts at 5 sessions)
       - Runtime (past year): 1.0 pt/hr (max 4 pts at 4 hrs)
    4. Machine Shop (12 pts max): Supplemental metalworking familiarity
       - General Auth (id 15): 4.0 pts
       - Specific Tool Auths (16, 33, 34, 41): 1.5 pts each (max 4.5 pts)
       - Sessions (past year): 0.5 pt/session (max 2 pts at 4 sessions)
       - Runtime (past year): 0.25 pt/hr (max 1.5 pts at 6 hrs)
    5. Other Lasers (3 pts max): Kern / Rabbit / FSL proficiency
       - Auth: 1 pt each (max 2 pts)
       - Usage: 0.2 pt/session (max 1 pt)
    """
    candidates = []
    already_authorized = []

    for mid, m_info in active_members.items():
        m_auths = authorizations.get(mid, {})

        # Check if already authorized for Fiber Laser
        has_fiber_auth = any(fid in m_auths for fid in target_fiber_ids)
        if has_fiber_auth:
            already_authorized.append(m_info)
            continue

        # --- UV LASER ---
        uv_auth = any(uid in m_auths for uid in uv_ids)
        uv_sessions = sum(usages.get((mid, uid), {}).get('sessions', 0) for uid in uv_ids)
        uv_runtime_secs = sum(usages.get((mid, uid), {}).get('runtime_secs', 0) for uid in uv_ids)

        uv_pts_auth = 15.0 if uv_auth else 0.0
        uv_pts_sess = min(12.0, uv_sessions * 1.5)
        uv_pts_time = min(8.0, (uv_runtime_secs / 3600.0) * 1.0)
        uv_score = round(uv_pts_auth + uv_pts_sess + uv_pts_time, 1)

        # --- EPILOG LASER ---
        epilog_auth = any(eid in m_auths for eid in epilog_ids)
        epilog_sessions = sum(usages.get((mid, eid), {}).get('sessions', 0) for eid in epilog_ids)
        epilog_runtime_secs = sum(usages.get((mid, eid), {}).get('runtime_secs', 0) for eid in epilog_ids)

        epilog_pts_auth = 10.0 if epilog_auth else 0.0
        epilog_pts_sess = min(10.0, epilog_sessions * 1.0)
        epilog_pts_time = min(10.0, (epilog_runtime_secs / 3600.0) * 0.5)
        epilog_score = round(epilog_pts_auth + epilog_pts_sess + epilog_pts_time, 1)

        # --- MOPA LASER ---
        mopa_auth = any(moid in m_auths for moid in mopa_ids)
        mopa_sessions = sum(usages.get((mid, moid), {}).get('sessions', 0) for moid in mopa_ids)
        mopa_runtime_secs = sum(usages.get((mid, moid), {}).get('runtime_secs', 0) for moid in mopa_ids)

        mopa_pts_auth = 8.0 if mopa_auth else 0.0
        mopa_pts_sess = min(8.0, mopa_sessions * 1.5)
        mopa_pts_time = min(4.0, (mopa_runtime_secs / 3600.0) * 1.0)
        mopa_score = round(mopa_pts_auth + mopa_pts_sess + mopa_pts_time, 1)

        # --- MACHINE SHOP ---
        ms_general_auth = (15 in m_auths)
        ms_spec_auth_count = sum(1 for ms_id in machineshop_ids if ms_id in m_auths and ms_id != 15)
        ms_sessions = sum(usages.get((mid, ms_id), {}).get('sessions', 0) for ms_id in machineshop_ids)
        ms_runtime_secs = sum(usages.get((mid, ms_id), {}).get('runtime_secs', 0) for ms_id in machineshop_ids)

        ms_pts_auth = (4.0 if ms_general_auth else 0.0) + min(4.5, ms_spec_auth_count * 1.5)
        ms_pts_sess = min(2.0, ms_sessions * 0.5)
        ms_pts_time = min(1.5, (ms_runtime_secs / 3600.0) * 0.25)
        ms_score = round(ms_pts_auth + ms_pts_sess + ms_pts_time, 1)

        # --- OTHER LASERS (Supplemental) ---
        other_auth_count = sum(1 for olid in other_laser_ids if olid in m_auths)
        other_sessions = sum(usages.get((mid, olid), {}).get('sessions', 0) for olid in other_laser_ids)

        other_pts_auth = min(2.0, other_auth_count * 1.0)
        other_pts_sess = min(1.0, other_sessions * 0.2)
        other_score = round(other_pts_auth + other_pts_sess, 1)

        # Total Composite Score
        total_score = round(uv_score + epilog_score + mopa_score + ms_score + other_score, 1)
        total_runtime_secs = uv_runtime_secs + epilog_runtime_secs + mopa_runtime_secs + ms_runtime_secs

        # Key qualification highlights
        highlights = []
        if uv_auth:
            highlights.append("UV Auth")
        if uv_sessions > 0:
            highlights.append(f"UV ({uv_sessions} sess)")
        if epilog_auth:
            highlights.append("Epilog Auth")
        if epilog_runtime_secs >= 3600 * 5:
            highlights.append(f"Epilog ({format_duration(epilog_runtime_secs)})")
        if mopa_auth:
            highlights.append("MOPA Auth")
        if ms_general_auth or ms_spec_auth_count > 0:
            ms_cnt_str = f"+{ms_spec_auth_count} tools" if ms_spec_auth_count > 0 else "General"
            highlights.append(f"Machine Shop ({ms_cnt_str})")

        candidates.append({
            'member_id': mid,
            'name': m_info['name'],
            'handle': m_info['handle'],
            'email': m_info['email'],
            'total_score': total_score,
            'uv_auth': uv_auth,
            'uv_sessions': uv_sessions,
            'uv_runtime_secs': uv_runtime_secs,
            'uv_score': uv_score,
            'epilog_auth': epilog_auth,
            'epilog_sessions': epilog_sessions,
            'epilog_runtime_secs': epilog_runtime_secs,
            'epilog_score': epilog_score,
            'mopa_auth': mopa_auth,
            'mopa_sessions': mopa_sessions,
            'mopa_runtime_secs': mopa_runtime_secs,
            'mopa_score': mopa_score,
            'ms_general_auth': ms_general_auth,
            'ms_spec_auth_count': ms_spec_auth_count,
            'ms_sessions': ms_sessions,
            'ms_runtime_secs': ms_runtime_secs,
            'ms_score': ms_score,
            'other_score': other_score,
            'total_runtime_secs': total_runtime_secs,
            'highlights': highlights
        })

    # Sort descending by score, breaking ties by UV score, Epilog score, MOPA score, total runtime, name
    candidates.sort(key=lambda x: (
        x['total_score'],
        x['uv_score'],
        x['epilog_score'],
        x['mopa_score'],
        x['total_runtime_secs'],
        -x['member_id']
    ), reverse=True)

    # Return top 75 and already authorized list
    return candidates[:75], already_authorized, len(candidates)


def render_html_report(top_candidates, already_authorized, total_candidates_count, since_date):
    """Generate high-impact executive HTML report."""
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

    # Stat counters among top candidates
    uv_users_cnt = sum(1 for c in top_candidates if c['uv_auth'] or c['uv_sessions'] > 0)
    epilog_users_cnt = sum(1 for c in top_candidates if c['epilog_auth'] or c['epilog_sessions'] > 0)
    mopa_users_cnt = sum(1 for c in top_candidates if c['mopa_auth'] or c['mopa_sessions'] > 0)
    ms_users_cnt = sum(1 for c in top_candidates if c['ms_general_auth'] or c['ms_spec_auth_count'] > 0 or c['ms_sessions'] > 0)
    top_tier_cnt = sum(1 for c in top_candidates if c['total_score'] >= 50.0)

    html = []
    # AGENTS.md rule: HTML reports must start with </pre> and end with <pre>
    # Also support the "HTML:" prefix recognized by reports.html
    html.append("HTML:")
    html.append("</pre>")
    html.append("""
    <div id="fiber-report-root" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background: #ffffff; padding: 24px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); max-width: 1200px; margin: 0 auto;">
        <!-- Header Section -->
        <div style="border-bottom: 2px solid #e2e8f0; padding-bottom: 20px; margin-bottom: 24px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 16px;">
            <div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="background: linear-gradient(135deg, #f59e0b, #d97706); color: white; padding: 6px 12px; border-radius: 8px; font-size: 13px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase;">Equipment Auth</span>
                    <h2 style="margin: 0; font-size: 24px; font-weight: 700; color: #0f172a;">Fiber Laser (xTool) Expedited Candidates</h2>
                </div>
                <p style="margin: 8px 0 0 0; color: #64748b; font-size: 14px;">
                    Top 75 active members recommended for expedited authorization based on <strong>UV software workflow (35%)</strong>, <strong>Epilog runtime (30%)</strong>, <strong>MOPA proficiency (20%)</strong>, and <strong>Machine Shop metalworking (12%)</strong>.
                </p>
                <div style="margin-top: 6px; font-size: 12px; color: #94a3b8;">
                    Usage focus: Since <strong>""" + escape(since_date) + """</strong> &bull; Generated: """ + escape(now_str) + """
                </div>
            </div>
            <div style="display: flex; gap: 10px; align-items: center;">
                <button type="button" onclick="exportFiberCandidatesCSV()" style="background: #0ea5e9; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5z"/><path d="M7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708l3 3z"/></svg>
                    Export CSV
                </button>
            </div>
        </div>

        <!-- Metric Summary Cards -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 24px;">
            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 18px;">
                <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: #64748b; letter-spacing: 0.5px;">Recommended</div>
                <div style="font-size: 26px; font-weight: 800; color: #0f172a; margin-top: 4px;">""" + str(len(top_candidates)) + """ <span style="font-size: 13px; font-weight: 400; color: #94a3b8;">/ """ + str(total_candidates_count) + """</span></div>
                <div style="font-size: 12px; color: #10b981; font-weight: 600; margin-top: 2px;">""" + str(top_tier_cnt) + """ High Priority (&ge;50 pts)</div>
            </div>
            <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 14px 18px;">
                <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: #1e40af; letter-spacing: 0.5px;">UV Laser (Flow Match)</div>
                <div style="font-size: 26px; font-weight: 800; color: #1d4ed8; margin-top: 4px;">""" + str(uv_users_cnt) + """</div>
                <div style="font-size: 12px; color: #3b82f6; margin-top: 2px;">Qualified / Active Users</div>
            </div>
            <div style="background: #faf5ff; border: 1px solid #e9d5ff; border-radius: 8px; padding: 14px 18px;">
                <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: #6b21a8; letter-spacing: 0.5px;">Epilog (Experience)</div>
                <div style="font-size: 26px; font-weight: 800; color: #7e22ce; margin-top: 4px;">""" + str(epilog_users_cnt) + """</div>
                <div style="font-size: 12px; color: #9333ea; margin-top: 2px;">Laser Veterans &amp; Runtime</div>
            </div>
            <div style="background: #fffbeb; border: 1px solid #fef3c7; border-radius: 8px; padding: 14px 18px;">
                <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: #92400e; letter-spacing: 0.5px;">MOPA Laser</div>
                <div style="font-size: 26px; font-weight: 800; color: #b45309; margin-top: 4px;">""" + str(mopa_users_cnt) + """</div>
                <div style="font-size: 12px; color: #d97706; margin-top: 2px;">Fiber/Galvo Proficiency</div>
            </div>
            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 14px 18px;">
                <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: #166534; letter-spacing: 0.5px;">Machine Shop</div>
                <div style="font-size: 26px; font-weight: 800; color: #15803d; margin-top: 4px;">""" + str(ms_users_cnt) + """</div>
                <div style="font-size: 12px; color: #16a34a; margin-top: 2px;">Metalworking Familiarity</div>
            </div>
        </div>

        <!-- Interactive Filter & Search Controls -->
        <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 16px; background: #f8fafc; padding: 12px 16px; border-radius: 8px; border: 1px solid #e2e8f0;">
            <div style="display: flex; align-items: center; gap: 8px; flex: 1; min-width: 240px;">
                <input type="text" id="fiber-search-input" onkeyup="filterFiberCandidatesTable()" placeholder="Search by member name, username, or highlight..." style="width: 100%; max-width: 320px; padding: 6px 12px; font-size: 13px; border: 1px solid #cbd5e1; border-radius: 6px;">
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="font-size: 12px; font-weight: 600; color: #64748b;">Filter:</span>
                <button type="button" onclick="setFiberFilterTier('all')" class="fiber-filter-btn" style="background: #0f172a; color: white; border: none; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer;">All (75)</button>
                <button type="button" onclick="setFiberFilterTier('top')" class="fiber-filter-btn" style="background: #e2e8f0; color: #334155; border: none; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer;">High Priority (&ge;50)</button>
                <button type="button" onclick="setFiberFilterTier('uv')" class="fiber-filter-btn" style="background: #e2e8f0; color: #334155; border: none; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer;">UV Users</button>
                <button type="button" onclick="setFiberFilterTier('epilog')" class="fiber-filter-btn" style="background: #e2e8f0; color: #334155; border: none; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer;">Epilog Heavy (&ge;10h)</button>
            </div>
        </div>

        <!-- Candidates Table -->
        <div style="overflow-x: auto; border: 1px solid #e2e8f0; border-radius: 8px;">
            <table id="fiber-candidates-table" style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
                <thead>
                    <tr style="background: #f1f5f9; border-bottom: 2px solid #cbd5e1; color: #334155;">
                        <th style="padding: 10px 14px; width: 50px; text-align: center;">Rank</th>
                        <th style="padding: 10px 14px; min-width: 180px;">Member</th>
                        <th style="padding: 10px 14px; width: 140px;">Composite Score</th>
                        <th style="padding: 10px 14px; min-width: 120px;">UV Laser (35%)</th>
                        <th style="padding: 10px 14px; min-width: 130px;">Epilog (30%)</th>
                        <th style="padding: 10px 14px; min-width: 110px;">MOPA (20%)</th>
                        <th style="padding: 10px 14px; min-width: 130px;">Machine Shop (12%)</th>
                        <th style="padding: 10px 14px;">Key Highlights</th>
                    </tr>
                </thead>
                <tbody>
    """)

    if not top_candidates:
        html.append("""
            <tr>
                <td colspan="8" style="padding: 30px; text-align: center; color: #64748b;">
                    No candidates found matching the qualification criteria.
                </td>
            </tr>
        """)

    for idx, c in enumerate(top_candidates, 1):
        score = c['total_score']
        # Tier badge styling
        if score >= 70:
            badge_bg = "#dcfce7"
            badge_fg = "#166534"
            badge_label = "Top Priority"
        elif score >= 50:
            badge_bg = "#dbeafe"
            badge_fg = "#1e40af"
            badge_label = "High Priority"
        elif score >= 30:
            badge_bg = "#f3e8ff"
            badge_fg = "#6b21a8"
            badge_label = "Recommended"
        else:
            badge_bg = "#f1f5f9"
            badge_fg = "#475569"
            badge_label = "Qualified"

        # Row background alternating
        row_bg = "#ffffff" if idx % 2 != 0 else "#f8fafc"

        # Rank badge
        if idx == 1:
            rank_display = '<span style="background: #f59e0b; color: white; padding: 2px 7px; border-radius: 10px; font-weight: 700; font-size: 11px;">#1</span>'
        elif idx == 2:
            rank_display = '<span style="background: #94a3b8; color: white; padding: 2px 7px; border-radius: 10px; font-weight: 700; font-size: 11px;">#2</span>'
        elif idx == 3:
            rank_display = '<span style="background: #b45309; color: white; padding: 2px 7px; border-radius: 10px; font-weight: 700; font-size: 11px;">#3</span>'
        else:
            rank_display = f'<span style="color: #64748b; font-weight: 600;">#{idx}</span>'

        # UV Laser pill
        if c['uv_auth']:
            uv_auth_badge = '<span style="background: #dcfce7; color: #15803d; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;">✓ Auth</span>'
        else:
            uv_auth_badge = '<span style="color: #94a3b8; font-size: 11px;">No Auth</span>'
        uv_usage_str = f"{c['uv_sessions']} sess, {format_duration(c['uv_runtime_secs'])}" if c['uv_sessions'] > 0 else '<span style="color:#94a3b8">0 sess</span>'

        # Epilog Laser pill
        if c['epilog_auth']:
            epilog_auth_badge = '<span style="background: #dcfce7; color: #15803d; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;">✓ Auth</span>'
        else:
            epilog_auth_badge = '<span style="color: #94a3b8; font-size: 11px;">No Auth</span>'
        epilog_usage_str = f"{c['epilog_sessions']} sess, {format_duration(c['epilog_runtime_secs'])}" if c['epilog_sessions'] > 0 else '<span style="color:#94a3b8">0 sess</span>'

        # MOPA Laser pill
        if c['mopa_auth']:
            mopa_auth_badge = '<span style="background: #dcfce7; color: #15803d; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;">✓ Auth</span>'
        else:
            mopa_auth_badge = '<span style="color: #94a3b8; font-size: 11px;">No Auth</span>'
        mopa_usage_str = f"{c['mopa_sessions']} sess, {format_duration(c['mopa_runtime_secs'])}" if c['mopa_sessions'] > 0 else '<span style="color:#94a3b8">0 sess</span>'

        # Machine Shop pill
        ms_auth_parts = []
        if c['ms_general_auth']:
            ms_auth_parts.append("Gen")
        if c['ms_spec_auth_count'] > 0:
            ms_auth_parts.append(f"+{c['ms_spec_auth_count']} tools")
        ms_auth_str = ", ".join(ms_auth_parts) if ms_auth_parts else '<span style="color:#94a3b8">No Auth</span>'
        if ms_auth_parts:
            ms_auth_badge = f'<span style="background: #dcfce7; color: #15803d; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;">✓ {ms_auth_str}</span>'
        else:
            ms_auth_badge = ms_auth_str
        ms_usage_str = f"{c['ms_sessions']} sess, {format_duration(c['ms_runtime_secs'])}" if c['ms_sessions'] > 0 else '<span style="color:#94a3b8">0 sess</span>'

        # Score progress bar width
        bar_pct = min(100, int(score))

        # Highlights badges
        hl_html = " ".join([
            f'<span style="background: #f1f5f9; color: #334155; padding: 2px 6px; border-radius: 4px; font-size: 10px; margin-right: 4px; white-space: nowrap; border: 1px solid #e2e8f0;">{escape(h)}</span>'
            for h in c['highlights']
        ]) if c['highlights'] else '<span style="color: #94a3b8; font-size: 11px;">General candidate</span>'

        # Extra data attributes for client-side filtering
        is_uv = "1" if (c['uv_auth'] or c['uv_sessions'] > 0) else "0"
        is_epilog_heavy = "1" if c['epilog_runtime_secs'] >= 36000 else "0"
        is_top = "1" if score >= 50.0 else "0"

        html.append(f"""
            <tr style="background: {row_bg}; border-bottom: 1px solid #e2e8f0;" data-tier="{badge_label.lower()}" data-is-top="{is_top}" data-is-uv="{is_uv}" data-is-epilog-heavy="{is_epilog_heavy}">
                <td style="padding: 10px 14px; text-align: center;">{rank_display}</td>
                <td style="padding: 10px 14px;">
                    <div style="font-weight: 600; color: #0f172a;">{escape(c['name'])}</div>
                    <div style="font-size: 11px; color: #64748b;">@{escape(c['handle'])}</div>
                </td>
                <td style="padding: 10px 14px;">
                    <div style="display: flex; align-items: baseline; gap: 6px;">
                        <span style="font-size: 17px; font-weight: 800; color: #0f172a;">{score}</span>
                        <span style="background: {badge_bg}; color: {badge_fg}; font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 4px;">{badge_label}</span>
                    </div>
                    <div style="background: #e2e8f0; height: 5px; border-radius: 3px; width: 100%; margin-top: 5px; overflow: hidden;">
                        <div style="background: linear-gradient(90deg, #3b82f6, #10b981); height: 100%; width: {bar_pct}%;"></div>
                    </div>
                </td>
                <td style="padding: 10px 14px;">
                    <div>{uv_auth_badge}</div>
                    <div style="font-size: 11px; color: #475569; margin-top: 3px;">{uv_usage_str}</div>
                    <div style="font-size: 10px; color: #94a3b8;">Pts: {c['uv_score']} / 35</div>
                </td>
                <td style="padding: 10px 14px;">
                    <div>{epilog_auth_badge}</div>
                    <div style="font-size: 11px; color: #475569; margin-top: 3px;">{epilog_usage_str}</div>
                    <div style="font-size: 10px; color: #94a3b8;">Pts: {c['epilog_score']} / 30</div>
                </td>
                <td style="padding: 10px 14px;">
                    <div>{mopa_auth_badge}</div>
                    <div style="font-size: 11px; color: #475569; margin-top: 3px;">{mopa_usage_str}</div>
                    <div style="font-size: 10px; color: #94a3b8;">Pts: {c['mopa_score']} / 20</div>
                </td>
                <td style="padding: 10px 14px;">
                    <div>{ms_auth_badge}</div>
                    <div style="font-size: 11px; color: #475569; margin-top: 3px;">{ms_usage_str}</div>
                    <div style="font-size: 10px; color: #94a3b8;">Pts: {c['ms_score']} / 12</div>
                </td>
                <td style="padding: 10px 14px;">
                    <div style="display: flex; flex-wrap: wrap; gap: 4px;">{hl_html}</div>
                </td>
            </tr>
        """)

    html.append("""
                </tbody>
            </table>
        </div>
    """)

    # Section for already authorized members
    if already_authorized:
        html.append("""
        <div style="margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 18px;">
            <details style="cursor: pointer;">
                <summary style="font-weight: 600; color: #64748b; font-size: 13px;">
                    Already Authorized on Fiber Laser (""" + str(len(already_authorized)) + """ members) &mdash; Excluded from recommendations
                </summary>
                <div style="margin-top: 10px; display: flex; flex-wrap: wrap; gap: 8px;">
        """)
        for m in already_authorized:
            html.append(f"""
                <span style="background: #f1f5f9; border: 1px solid #cbd5e1; color: #334155; padding: 4px 10px; border-radius: 6px; font-size: 12px;">
                    {escape(m['name'])} (@{escape(m['handle'])})
                </span>
            """)
        html.append("""
                </div>
            </details>
        </div>
        """)

    # Rubric Explanation Footnote
    html.append("""
        <div style="margin-top: 24px; padding: 14px 18px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 12px; color: #64748b; line-height: 1.6;">
            <strong>Scoring Methodology (100 Point Max Scale):</strong>
            <ul style="margin: 6px 0 0 16px; padding: 0;">
                <li><strong>UV Laser (Weight: 35%)</strong>: 15 pts for authorization, up to 12 pts for logged sessions (1.5 pts/sess), up to 8 pts for runtime (1 pt/hr). Matches software workflow.</li>
                <li><strong>Epilog Laser (Weight: 30%)</strong>: 10 pts for authorization, up to 10 pts for sessions (1 pt/sess), up to 10 pts for runtime (0.5 pt/hr up to 20h). Reflects laser runtime mastery.</li>
                <li><strong>MOPA Laser (Weight: 20%)</strong>: 8 pts for authorization, up to 8 pts for sessions (1.5 pts/sess), up to 4 pts for runtime (1 pt/hr). Reflects galvo/pulsed fiber laser proficiency.</li>
                <li><strong>Machine Shop (Weight: 12%)</strong>: 4 pts for General auth, up to 4.5 pts for specific tools (mill/lathe), up to 3.5 pts for usage. Reflects metalworking familiarity.</li>
                <li><strong>Supplemental Lasers (Weight: 3%)</strong>: Up to 3 pts for Kern, Rabbit, or FSL authorizations &amp; usage.</li>
            </ul>
        </div>
    </div>

    <!-- Client-side Search and CSV Export Script -->
    <script>
    function filterFiberCandidatesTable() {
        var input = document.getElementById('fiber-search-input');
        var filter = input.value.toLowerCase();
        var table = document.getElementById('fiber-candidates-table');
        var tr = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');

        for (var i = 0; i < tr.length; i++) {
            var text = tr[i].innerText.toLowerCase();
            if (text.indexOf(filter) > -1) {
                tr[i].style.display = "";
            } else {
                tr[i].style.display = "none";
            }
        }
    }

    function setFiberFilterTier(tier) {
        var buttons = document.querySelectorAll('.fiber-filter-btn');
        buttons.forEach(function(b) {
            b.style.background = '#e2e8f0';
            b.style.color = '#334155';
        });
        if (event && event.target) {
            event.target.style.background = '#0f172a';
            event.target.style.color = '#ffffff';
        }

        var table = document.getElementById('fiber-candidates-table');
        var tr = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');

        for (var i = 0; i < tr.length; i++) {
            var row = tr[i];
            if (tier === 'all') {
                row.style.display = "";
            } else if (tier === 'top') {
                row.style.display = (row.getAttribute('data-is-top') === '1') ? "" : "none";
            } else if (tier === 'uv') {
                row.style.display = (row.getAttribute('data-is-uv') === '1') ? "" : "none";
            } else if (tier === 'epilog') {
                row.style.display = (row.getAttribute('data-is-epilog-heavy') === '1') ? "" : "none";
            }
        }
    }

    function exportFiberCandidatesCSV() {
        var rows = [
            ["Rank", "Member Name", "Username", "Composite Score", "UV Auth", "UV Sessions", "UV Runtime (hrs)", "Epilog Auth", "Epilog Sessions", "Epilog Runtime (hrs)", "MOPA Auth", "MOPA Sessions", "MOPA Runtime (hrs)", "Machine Shop General", "Machine Shop Tool Count", "Machine Shop Sessions", "Machine Shop Runtime (hrs)"]
        ];

        var table = document.getElementById('fiber-candidates-table');
        var tr = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');
        for (var i = 0; i < tr.length; i++) {
            var cols = tr[i].querySelectorAll('td');
            if (cols.length < 8) continue;
            var rank = cols[0].innerText.replace('#', '').trim();
            var nameParts = cols[1].innerText.split('\\n');
            var name = nameParts[0].trim();
            var handle = (nameParts.length > 1) ? nameParts[1].replace('@', '').trim() : '';
            var score = cols[2].innerText.split('\\n')[0].trim();

            rows.push([
                rank,
                '"' + name.replace(/"/g, '""') + '"',
                '"' + handle.replace(/"/g, '""') + '"',
                score,
                cols[3].innerText.includes('✓ Auth') ? 'Yes' : 'No',
                cols[3].innerText,
                cols[4].innerText.includes('✓ Auth') ? 'Yes' : 'No',
                cols[4].innerText,
                cols[5].innerText.includes('✓ Auth') ? 'Yes' : 'No',
                cols[5].innerText,
                cols[6].innerText.includes('✓') ? 'Yes' : 'No',
                cols[6].innerText
            ]);
        }

        var csvContent = "data:text/csv;charset=utf-8," + rows.map(function(e) { return e.join(","); }).join("\\n");
        var encodedUri = encodeURI(csvContent);
        var link = document.createElement("a");
        link.setAttribute("href", encodedUri);
        link.setAttribute("download", "fiber_laser_candidates_" + new Date().toISOString().slice(0,10) + ".csv");
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
    </script>
    """)
    # Closing pre tag required by AGENTS.md rule
    html.append("<pre>")

    return "\n".join(html)


def main():
    if not os.path.exists(MAKEIT_DB):
        print(f"HTML:<div style='padding:20px; color:#b91c1c; background:#fef2f2; border:1px solid #fecaca; border-radius:8px;'><strong>Error:</strong> Main database file not found at <code>{escape(MAKEIT_DB)}</code>.</div>")
        sys.exit(1)

    try:
        conn = sqlite3.connect(MAKEIT_DB)
        cursor = conn.cursor()

        # Attach log database if present
        has_logdb = False
        if os.path.exists(LOG_DB):
            try:
                conn.execute(f'ATTACH DATABASE "{LOG_DB}" AS logdb')
                has_logdb = True
            except Exception as e:
                sys.stderr.write(f"Warning: Could not attach log.db: {e}\n")

        # Verify members table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='members'")
        if not cursor.fetchone():
            print("HTML:<div style='padding:20px; color:#b45309; background:#fffbeb; border:1px solid #fef3c7; border-radius:8px;'><strong>Notice:</strong> Table <code>members</code> not found in <code>makeit.db</code>. This report requires the production member database.</div>")
            sys.exit(0)

        # Usage lookback date focus
        since_date_env = os.environ.get('REPORT_SINCE', '').strip()
        if since_date_env:
            since_date = since_date_env
        else:
            # Default to 1 year (365 days) ago
            since_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

        # 1. Resolve resource IDs
        target_fiber_ids, uv_ids, epilog_ids, mopa_ids, machineshop_ids, other_laser_ids, _ = resolve_resources(cursor)

        # 2. Get active members
        active_members = get_active_members(cursor)

        # 3. Get authorizations
        authorizations = get_authorizations(cursor)

        # 4. Get usages over the past year
        usages = get_usages(cursor, since_date, has_logdb)

        # 5. Compute candidate scores & top 75
        top_candidates, already_authorized, total_candidates_count = calculate_candidate_scores(
            active_members, authorizations, usages,
            target_fiber_ids, uv_ids, epilog_ids, mopa_ids,
            machineshop_ids, other_laser_ids
        )

        conn.close()

        # 6. Render HTML report
        report_html = render_html_report(top_candidates, already_authorized, total_candidates_count, since_date)
        print(report_html)
        sys.exit(0)

    except Exception as e:
        print(f"HTML:<div style='padding:20px; color:#b91c1c; background:#fef2f2; border:1px solid #fecaca; border-radius:8px;'><strong>Database error generating report:</strong> {escape(str(e))}</div>")
        sys.exit(1)


if __name__ == "__main__":
    main()
