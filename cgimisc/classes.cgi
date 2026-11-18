#!/usr/bin/env python3
"""
MakeIt Labs - Standalone Classes & Workshop CGI Board
Free-standing CGI script for Apache / web servers.
Fetches live classes from Eventbrite API, caches locally, and renders
a responsive flexbox/grid layout for mobile, tablet, and desktop displays.
Includes real MakeIt Labs logo, sold-out badging, and toggle filters.
"""

import os
import sys
import json
import time
import tempfile
import base64
import urllib.request
import urllib.error
import datetime
from collections import defaultdict

# ---------------------------------------------------------------------------
# Directory & Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

ORG_ID = "27283320655"
TOKEN = None
CACHE_FILE = os.path.join(os.path.expanduser("~"), ".cache", "makeit_classboard_cache.json")
if not os.path.exists(os.path.dirname(CACHE_FILE)):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    except Exception:
        CACHE_FILE = "/tmp/makeit_classboard_cache.json"

CACHE_TTL_SECONDS = 14400  # 4 hours cache
EVENTBRITE_PROFILE_URL = "https://www.eventbrite.com/o/makeit-labs-1932299069"

# Attempt to load credentials from vars.py or var.py in same directory or parent
config_vars = None
try:
    import vars as config_vars
except ImportError:
    try:
        import var as config_vars
    except ImportError:
        config_vars = None

if config_vars:
    if hasattr(config_vars, 'ORG_ID') and config_vars.ORG_ID:
        ORG_ID = config_vars.ORG_ID
    if hasattr(config_vars, 'TOKEN') and config_vars.TOKEN:
        TOKEN = config_vars.TOKEN

if not TOKEN:
    TOKEN = os.environ.get("EVENTBRITE_TOKEN") or os.environ.get("TOKEN")

# ---------------------------------------------------------------------------
# Category Mapping
# ---------------------------------------------------------------------------
CATEGORIES = [
    ("all", "All Classes"),
    ("woodworking", "Woodworking"),
    ("metalworking", "Metal & Welding"),
    ("laser-cnc", "Laser & CNC"),
    ("ceramics-arts", "Ceramics & Crafts"),
    ("digital-cad", "CAD & Digital"),
    ("orientations", "Orientations & Safety")
]

def categorize_class(name):
    n = name.lower()
    cats = []
    if any(k in n for k in ["wood", "lathe orientation", "shopbot"]):
        cats.append("woodworking")
    if any(k in n for k in ["weld", "metal", "machin", "mill", "trak", "bridgeport", "pewter"]):
        cats.append("metalworking")
    if any(k in n for k in ["laser", "kern", "epilog", "mopa", "fiber", "cnc", "router", "waterjet"]):
        cats.append("laser-cnc")
    if any(k in n for k in ["ceramic", "glaz", "glass", "pottery", "art", "jewelry", "wire wrap", "apparel", "mat board", "ornament"]):
        cats.append("ceramics-arts")
    if any(k in n for k in ["cad", "onshape", "blender", "inkscape", "design tools", "software"]):
        cats.append("digital-cad")
    if any(k in n for k in ["orient", "safety", "authoriz", "walkthrough", "intro", "101", "basics"]):
        cats.append("orientations")
    if not cats:
        cats.append("all")
    return cats

# ---------------------------------------------------------------------------
# MakeIt Labs Official Logo Loader (SVG with embedded fallback)
# ---------------------------------------------------------------------------
def get_logo_html():
    possible_paths = [
        os.path.join(SCRIPT_DIR, "..", "html", "MakeIt Labs Logo 2016.svg"),
        os.path.join(SCRIPT_DIR, "static", "MakeIt Labs Logo 2016.svg"),
        os.path.join(SCRIPT_DIR, "MakeIt Labs Logo 2016.svg"),
        os.path.join(SCRIPT_DIR, "..", "static", "makeit.png"),
        os.path.join(SCRIPT_DIR, "static", "makeit.png"),
        os.path.join(SCRIPT_DIR, "makeit.png")
    ]
    for p in possible_paths:
        if os.path.exists(p):
            if p.endswith(".svg"):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        svg_data = f.read()
                        if "viewBox" not in svg_data:
                            svg_data = svg_data.replace("<svg", '<svg viewBox="0 0 738.03394 130.13995"', 1)
                        import re
                        svg_data = re.sub(r'<\?xml[^>]*\?>', '', svg_data)
                        svg_data = re.sub(r'<!--.*?-->', '', svg_data, flags=re.DOTALL).strip()
                        return f'<div class="brand-logo-wrap" title="MakeIt Labs">{svg_data}</div>'
                except Exception:
                    pass
            elif p.endswith(".png"):
                try:
                    with open(p, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                        return f'<div class="brand-logo-wrap" title="MakeIt Labs"><img src="data:image/png;base64,{b64}" alt="MakeIt Labs Logo" class="brand-logo-img"></div>'
                except Exception:
                    pass

    # Self-contained fallback SVG if static directory is not mounted
    return '''<div class="brand-logo-wrap" title="MakeIt Labs">
        <svg viewBox="0 0 24 24" class="brand-fallback-bulb">
            <path d="M12 2a7 7 0 0 0-7 7c0 2.38 1.19 4.47 3 5.74V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.26c1.81-1.27 3-3.36 3-5.74a7 7 0 0 0-7-7zM9 21a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1v-1H9v1z"/>
        </svg>
        <span class="brand-fallback-text">MAKEIT LABS</span>
    </div>'''

# ---------------------------------------------------------------------------
# Eventbrite API Client & Caching
# ---------------------------------------------------------------------------
def load_cache():
    for path in (CACHE_FILE, "/tmp/makeit_classboard_cache.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if time.time() - data.get("timestamp", 0) < CACHE_TTL_SECONDS:
                    return data.get("classes"), data.get("last_updated")
        except Exception:
            continue
    return None, None

def save_cache(classes, last_updated):
    global CACHE_FILE
    cache_dir = os.path.dirname(os.path.abspath(CACHE_FILE))
    temp_path = None
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except Exception:
        cache_dir = "/tmp"
        CACHE_FILE = "/tmp/makeit_classboard_cache.json"

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=cache_dir,
            delete=False,
            encoding="utf-8",
            prefix=".classboard_cache_",
            suffix=".tmp"
        ) as f:
            temp_path = f.name
            json.dump({
                "timestamp": time.time(),
                "last_updated": last_updated,
                "classes": classes
            }, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, CACHE_FILE)
    except Exception:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

def fetch_events_from_eventbrite(force_refresh=False):
    if not force_refresh:
        cached_classes, last_updated = load_cache()
        if cached_classes is not None:
            return cached_classes, last_updated

    if not TOKEN:
        # Fall back to existing cache if token is not available
        cached_classes, last_updated = load_cache()
        if cached_classes is not None:
            return cached_classes, last_updated
        raise RuntimeError("Eventbrite TOKEN is not configured (missing in vars.py)")

    all_events = []
    page = 1
    base_url = f"https://www.eventbriteapi.com/v3/organizations/{ORG_ID}/events/?status=live,started&token={TOKEN}&expand=ticket_availability,logo"

    try:
        while True:
            req = urllib.request.Request(
                f"{base_url}&page={page}",
                headers={"User-Agent": "MakeItLabs-ClassBoard/2.0"}
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                events = data.get("events", [])
                all_events.extend(events)
                if not data.get("pagination", {}).get("has_more_items"):
                    break
                page += 1
                if page > 10:  # safety cap
                    break
    except Exception as e:
        for path in (CACHE_FILE, "/tmp/makeit_classboard_cache.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("classes", []), data.get("last_updated", "Cached")
            except Exception:
                continue
        raise RuntimeError(f"Eventbrite API request failed: {e}")

    now_dt = datetime.datetime.now()
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
    now_date_str = now_dt.strftime("%Y-%m-%d")

    groups = defaultdict(list)
    for e in all_events:
        key = e.get("series_id") or e.get("id")
        groups[key].append(e)

    classes = []
    for key, items in groups.items():
        # Keep upcoming instances where start date/time is today or in the future
        upcoming_items = [
            x for x in items
            if x.get("start", {}).get("local", "") >= now_iso
            or x.get("start", {}).get("local", "")[:10] >= now_date_str
        ]
        if not upcoming_items:
            continue

        upcoming_items.sort(key=lambda x: x.get("start", {}).get("local", ""))
        next_item = upcoming_items[0]

        start_str = next_item.get("start", {}).get("local", "")
        try:
            next_dt = datetime.datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S")
        except Exception:
            next_dt = datetime.datetime.now()

        formatted_day = next_dt.strftime("%A, %B %d")
        time_part = next_dt.strftime("%I:%M %p").lstrip("0")
        formatted_date = f"{formatted_day} • {time_part}"

        title = next_item.get("name", {}).get("text", "Untitled Workshop").strip()

        logo_url = None
        if next_item.get("logo"):
            logo_obj = next_item["logo"]
            logo_url = logo_obj.get("original", {}).get("url") or logo_obj.get("url")

        summary = next_item.get("summary") or ""
        if not summary and next_item.get("description", {}).get("text"):
            summary = next_item["description"]["text"][:140].strip() + "..."

        cats = categorize_class(title)

        # Calculate sold out status across upcoming instances
        available_items = [
            x for x in upcoming_items
            if not x.get("ticket_availability", {}).get("is_sold_out", False)
        ]
        available_count = len(available_items)
        all_sold = (available_count == 0)
        any_sold = (len(upcoming_items) > available_count)

        # Check waitlist on next or upcoming item
        waitlist_available = any(
            bool(x.get("ticket_availability", {}).get("waitlist_available", False))
            for x in upcoming_items
        )

        # Prefer master series URL for recurring classes so Eventbrite shows all dates,
        # or link to the first open date if not a series
        series_id = next_item.get("series_id")
        base_item_url = next_item.get("url") or EVENTBRITE_PROFILE_URL

        if series_id:
            if "tickets-" in base_item_url:
                event_url = re.sub(r"tickets-\d+", f"tickets-{series_id}", base_item_url)
            else:
                event_url = f"https://www.eventbrite.com/e/{series_id}"
        elif available_items and available_items[0].get("url"):
            event_url = available_items[0]["url"]
        else:
            event_url = base_item_url

        if event_url.startswith("http://"):
            event_url = "https://" + event_url[7:]

        if logo_url and logo_url.startswith("http://"):
            logo_url = "https://" + logo_url[7:]

        classes.append({
            "id": next_item.get("id"),
            "series_id": next_item.get("series_id"),
            "title": title,
            "url": event_url,
            "logo_url": logo_url,
            "summary": summary,
            "count": len(upcoming_items),
            "available_count": available_count,
            "all_sold": all_sold,
            "any_sold": any_sold,
            "waitlist_available": waitlist_available,
            "next_dt_iso": next_dt.isoformat(),
            "formatted_date": formatted_date,
            "weekday": next_dt.strftime("%A"),
            "time_str": time_part,
            "categories": cats
        })

    classes.sort(key=lambda x: x["next_dt_iso"])
    last_updated = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")
    save_cache(classes, last_updated)
    return classes, last_updated

# ---------------------------------------------------------------------------
# HTML Page Rendering
# ---------------------------------------------------------------------------
def render_classes_page(force_refresh=False):
    error_msg = None
    try:
        classes, last_updated = fetch_events_from_eventbrite(force_refresh=force_refresh)
    except Exception as e:
        classes = []
        last_updated = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")
        error_msg = f"Unable to fetch classes from Eventbrite: {e}"

    total_count = len(classes)
    sold_out_count = sum(1 for c in classes if c["all_sold"])
    logo_html = get_logo_html()

    cards_html = []
    for c in classes:
        cats_str = " ".join(c["categories"])
        is_sold_out = c["all_sold"]

        # Build badges
        badges_html = []
        if is_sold_out:
            if c["waitlist_available"]:
                badges_html.append('<span class="badge badge-waitlist">Waitlist Available</span>')
            else:
                badges_html.append('<span class="badge badge-soldout">Sold Out</span>')
        else:
            if c["count"] > 1:
                if c["any_sold"]:
                    badges_html.append(f'<span class="badge badge-multi">{c["count"]} dates ({c["available_count"]} open)</span>')
                else:
                    badges_html.append(f'<span class="badge badge-multi">{c["count"]} dates available</span>')
            else:
                badges_html.append('<span class="badge badge-single">Tickets Available</span>')

        badges_joined = "".join(badges_html)

        if c["logo_url"]:
            img_tag = f'<img src="{c["logo_url"]}" alt="{c["title"]}" loading="lazy" class="card-img">'
        else:
            img_tag = '''
            <div class="card-img-placeholder">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                </svg>
                <span>MakeIt Labs Class</span>
            </div>'''

        summary_p = f'<p class="card-summary">{c["summary"]}</p>' if c["summary"] else ''

        # Action button text & styling
        if is_sold_out:
            if c["waitlist_available"]:
                btn_text = "Join Waitlist on Eventbrite"
                btn_class = "btn-register btn-waitlist"
            else:
                btn_text = "Sold Out &bull; View on Eventbrite"
                btn_class = "btn-register btn-soldout"
        else:
            if c["count"] > 1:
                btn_text = "Select a Date on Eventbrite"
                btn_class = "btn-register"
            else:
                btn_text = "Register on Eventbrite"
                btn_class = "btn-register"

        soldout_attr = "true" if is_sold_out else "false"
        card_extra_class = "is-sold-out" if is_sold_out else ""

        card_html = f'''
        <article class="class-card {card_extra_class}" data-title="{c["title"].lower()}" data-cats="{cats_str}" data-soldout="{soldout_attr}">
            <a href="{c["url"]}" target="_blank" rel="noopener noreferrer" class="card-link" aria-label="Register for {c["title"]}">
                <div class="card-media">
                    {img_tag}
                    <div class="card-overlay-badges">
                        {badges_joined}
                    </div>
                </div>
                <div class="card-body">
                    <div class="date-header">
                        <svg class="icon-clock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <polyline points="12 6 12 12 16 14"/>
                        </svg>
                        <div class="date-details">
                            <span class="next-label">{"Next Class" if c["count"] > 1 else "Class Date"}</span>
                            <span class="date-value">{c["formatted_date"]}</span>
                        </div>
                    </div>
                    <h2 class="card-title">{c["title"]}</h2>
                    {summary_p}
                    <div class="card-action">
                        <span class="{btn_class}">
                            <span>{btn_text}</span>
                            <svg class="icon-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="5" y1="12" x2="19" y2="12"/>
                                <polyline points="12 5 19 12 12 19"/>
                            </svg>
                        </span>
                    </div>
                </div>
            </a>
        </article>'''
        cards_html.append(card_html)

    cards_joined = "\n".join(cards_html)

    filter_buttons = []
    for cat_id, cat_name in CATEGORIES:
        active_class = "active" if cat_id == "all" else ""
        filter_buttons.append(
            f'<button type="button" class="filter-pill {active_class}" data-filter="{cat_id}">{cat_name}</button>'
        )
    filter_pills_html = "\n".join(filter_buttons)

    error_banner = ""
    if error_msg:
        error_banner = f'''
        <div class="alert-banner">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span>{error_msg}</span>
        </div>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MakeIt Labs Classes &amp; Workshops</title>
    <meta name="description" content="Explore hands-on classes, tool authorizations, and creative workshops at MakeIt Labs in Nashua, NH.">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-base: #f8fafc;
            --bg-surface: #ffffff;
            --bg-card: #ffffff;
            --bg-card-hover: #ffffff;
            --border-subtle: #e2e8f0;
            --border-strong: #cbd5e1;
            --border-focus: #0284c7;
            --text-main: #0f172a;
            --text-muted: #475569;
            --text-dim: #64748b;
            --accent-cyan: #0284c7;
            --accent-blue: #2563eb;
            --accent-amber: #d97706;
            --accent-emerald: #059669;
            --accent-rose: #e11d48;
            --accent-glow: rgba(2, 132, 199, 0.12);
            --radius-sm: 8px;
            --radius-md: 14px;
            --radius-lg: 20px;
            --shadow-card: 0 1px 3px rgba(0, 0, 0, 0.05), 0 4px 14px rgba(0, 0, 0, 0.03);
            --shadow-hover: 0 16px 32px -6px rgba(0, 0, 0, 0.1), 0 4px 12px -2px rgba(0, 0, 0, 0.04);
            --transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        *, *::before, *::after {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            min-height: 100vh;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            overflow-x: hidden;
        }}

        .page-ambient {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 480px;
            background: radial-gradient(circle at 50% -20%, rgba(2, 132, 199, 0.07), transparent 70%),
                        radial-gradient(circle at 85% 10%, rgba(245, 158, 11, 0.04), transparent 50%);
            pointer-events: none;
            z-index: 0;
        }}

        .container {{
            position: relative;
            z-index: 1;
            width: 100%;
            max-width: 1720px;
            margin: 0 auto;
            padding: 1.5rem 1.25rem 4rem;
        }}

        /* Header Navigation */
        header.site-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 1.25rem;
            padding-bottom: 1.75rem;
            border-bottom: 1px solid var(--border-subtle);
            margin-bottom: 2rem;
        }}

        .brand-block {{
            display: flex;
            align-items: center;
            gap: 1.25rem;
            text-decoration: none;
            color: inherit;
        }}

        /* Official MakeIt Labs Logo (Directly on light background, no white box needed) */
        .brand-logo-wrap {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            height: 48px;
            flex-shrink: 0;
            padding: 0;
            background: transparent;
        }}

        .brand-logo-wrap svg {{
            height: 38px;
            width: auto;
            max-width: 230px;
            display: block;
        }}

        .brand-logo-wrap img.brand-logo-img {{
            height: 38px;
            width: auto;
            max-width: 230px;
            display: block;
            object-fit: contain;
        }}

        .brand-fallback-bulb {{
            width: 26px;
            height: 26px;
            fill: #e68726;
            margin-right: 0.35rem;
        }}

        .brand-fallback-text {{
            font-family: 'Outfit', sans-serif;
            font-weight: 800;
            color: #283b96;
            font-size: 1.15rem;
            letter-spacing: -0.02em;
        }}

        .brand-text h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.5rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            color: #0f172a;
        }}

        .brand-text p {{
            font-size: 0.85rem;
            color: var(--text-dim);
            font-weight: 500;
        }}

        .header-actions {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}

        .btn-header {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.6rem 1.15rem;
            border-radius: var(--radius-sm);
            font-size: 0.875rem;
            font-weight: 600;
            text-decoration: none;
            transition: var(--transition);
            border: 1px solid var(--border-strong);
            background-color: #ffffff;
            color: var(--text-main);
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
        }}

        .btn-header:hover {{
            background-color: #f1f5f9;
            border-color: #94a3b8;
            transform: translateY(-1px);
        }}

        .btn-header-primary {{
            background: linear-gradient(135deg, #0284c7, #2563eb);
            border-color: transparent;
            color: #ffffff;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
        }}

        .btn-header-primary:hover {{
            background: linear-gradient(135deg, #0369a1, #1d4ed8);
            box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
        }}

        /* Hero Controls: Search & Filters */
        .controls-panel {{
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
            margin-bottom: 2.25rem;
            background: #ffffff;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            padding: 1.25rem 1.5rem;
            box-shadow: var(--shadow-card);
        }}

        .search-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            flex-wrap: wrap;
        }}

        .search-box {{
            position: relative;
            flex: 1;
            min-width: 260px;
        }}

        .search-box svg {{
            position: absolute;
            left: 1rem;
            top: 50%;
            transform: translateY(-50%);
            width: 20px;
            height: 20px;
            color: var(--text-dim);
            pointer-events: none;
        }}

        .search-box input {{
            width: 100%;
            padding: 0.75rem 1rem 0.75rem 2.85rem;
            background: #f8fafc;
            border: 1px solid var(--border-strong);
            border-radius: var(--radius-sm);
            color: var(--text-main);
            font-size: 0.95rem;
            outline: none;
            transition: var(--transition);
        }}

        .search-box input:focus {{
            background: #ffffff;
            border-color: var(--border-focus);
            box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.15);
        }}

        .search-box input::placeholder {{
            color: #94a3b8;
        }}

        .controls-right {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            flex-wrap: wrap;
        }}

        /* Toggle Sold Out Button */
        .btn-toggle-soldout {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.55rem 0.95rem;
            border-radius: var(--radius-sm);
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            border: 1px solid var(--border-strong);
            background: #ffffff;
            color: var(--text-muted);
            transition: var(--transition);
            user-select: none;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
        }}

        .btn-toggle-soldout:hover {{
            background: #f1f5f9;
            color: var(--text-main);
            border-color: #94a3b8;
        }}

        .btn-toggle-soldout.active {{
            background: #fff1f2;
            border-color: #fda4af;
            color: #be123c;
            box-shadow: 0 1px 3px rgba(225, 29, 72, 0.1);
        }}

        .stats-badge {{
            font-size: 0.85rem;
            color: var(--text-muted);
            white-space: nowrap;
            background: #f1f5f9;
            padding: 0.55rem 0.85rem;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border-subtle);
        }}

        .stats-badge strong {{
            color: var(--accent-cyan);
            font-weight: 700;
        }}

        /* Filter Pills */
        .filter-pills {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
            overflow-x: auto;
            padding-bottom: 0.25rem;
        }}

        .filter-pill {{
            background: #f8fafc;
            border: 1px solid var(--border-strong);
            color: #475569;
            padding: 0.45rem 1rem;
            border-radius: 9999px;
            font-size: 0.825rem;
            font-weight: 600;
            cursor: pointer;
            transition: var(--transition);
            white-space: nowrap;
        }}

        .filter-pill:hover {{
            background: #f1f5f9;
            color: var(--text-main);
            border-color: #94a3b8;
        }}

        .filter-pill.active {{
            background: linear-gradient(135deg, #0284c7, #2563eb);
            color: #ffffff;
            border-color: transparent;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
        }}

        /* The Grid */
        .classes-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(min(100%, 330px), 1fr));
            gap: 1.5rem;
        }}

        /* Card Component */
        .class-card {{
            background: #ffffff;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: var(--transition);
            box-shadow: var(--shadow-card);
        }}

        .class-card:hover {{
            transform: translateY(-5px);
            border-color: #7dd3fc;
            box-shadow: var(--shadow-hover);
        }}

        .class-card.is-sold-out {{
            border-color: #fecdd3;
            background: #fffafa;
        }}

        .class-card.is-sold-out:hover {{
            border-color: #fda4af;
            box-shadow: 0 16px 32px -6px rgba(225, 29, 72, 0.12), 0 4px 12px -2px rgba(225, 29, 72, 0.05);
        }}

        .card-link {{
            text-decoration: none;
            color: inherit;
            display: flex;
            flex-direction: column;
            height: 100%;
        }}

        .card-media {{
            position: relative;
            width: 100%;
            aspect-ratio: 16 / 9;
            background: #e2e8f0;
            overflow: hidden;
        }}

        .card-img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.4s ease;
        }}

        .class-card:hover .card-img {{
            transform: scale(1.04);
        }}

        .class-card.is-sold-out .card-img {{
            filter: grayscale(35%) contrast(95%);
            opacity: 0.88;
        }}

        .card-img-placeholder {{
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            color: var(--text-dim);
            background: linear-gradient(135deg, #f1f5f9, #e2e8f0);
            font-size: 0.85rem;
            font-weight: 600;
        }}

        .card-overlay-badges {{
            position: absolute;
            top: 0.75rem;
            left: 0.75rem;
            display: flex;
            gap: 0.4rem;
            flex-wrap: wrap;
            z-index: 2;
        }}

        .badge {{
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.3rem 0.65rem;
            border-radius: 9999px;
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            letter-spacing: 0.01em;
        }}

        .badge-soldout {{
            background: rgba(225, 29, 72, 0.94);
            color: #ffffff;
            box-shadow: 0 2px 8px rgba(225, 29, 72, 0.35);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .badge-waitlist {{
            background: rgba(217, 119, 6, 0.94);
            color: #ffffff;
            box-shadow: 0 2px 8px rgba(217, 119, 6, 0.35);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .badge-multi {{
            background: rgba(5, 150, 105, 0.92);
            color: #ffffff;
            box-shadow: 0 2px 8px rgba(5, 150, 105, 0.3);
        }}

        .badge-single {{
            background: rgba(15, 23, 42, 0.82);
            color: #f8fafc;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}

        .card-body {{
            padding: 1.25rem 1.35rem;
            display: flex;
            flex-direction: column;
            flex-grow: 1;
            gap: 0.75rem;
        }}

        .date-header {{
            display: flex;
            align-items: flex-start;
            gap: 0.65rem;
            color: var(--accent-amber);
            font-size: 0.85rem;
        }}

        .icon-clock {{
            width: 18px;
            height: 18px;
            flex-shrink: 0;
            margin-top: 0.15rem;
            color: #d97706;
        }}

        .date-details {{
            display: flex;
            flex-direction: column;
        }}

        .next-label {{
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-dim);
        }}

        .date-value {{
            font-weight: 700;
            color: #1e293b;
        }}

        .card-title {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.15rem;
            font-weight: 700;
            line-height: 1.35;
            color: #0f172a;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            transition: color 0.15s ease;
        }}

        .class-card:hover .card-title {{
            color: var(--accent-cyan);
        }}

        .card-summary {{
            font-size: 0.85rem;
            color: var(--text-muted);
            line-height: 1.45;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            margin-top: 0.15rem;
        }}

        .card-action {{
            margin-top: auto;
            padding-top: 0.75rem;
            border-top: 1px solid #f1f5f9;
        }}

        .btn-register {{
            display: inline-flex;
            align-items: center;
            justify-content: space-between;
            width: 100%;
            padding: 0.65rem 0.95rem;
            background: #f8fafc;
            border: 1px solid var(--border-strong);
            border-radius: var(--radius-sm);
            color: #0369a1;
            font-size: 0.85rem;
            font-weight: 600;
            transition: var(--transition);
        }}

        .class-card:hover .btn-register {{
            background: linear-gradient(135deg, #0284c7, #2563eb);
            border-color: transparent;
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        }}

        .btn-register.btn-soldout {{
            color: #be123c;
            background: #fff1f2;
            border-color: #fecdd3;
        }}

        .class-card:hover .btn-register.btn-soldout {{
            background: linear-gradient(135deg, #e11d48, #be123c);
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(225, 29, 72, 0.3);
        }}

        .btn-register.btn-waitlist {{
            color: #b45309;
            background: #fffbeb;
            border-color: #fde68a;
        }}

        .class-card:hover .btn-register.btn-waitlist {{
            background: linear-gradient(135deg, #d97706, #b45309);
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(217, 119, 6, 0.3);
        }}

        .icon-arrow {{
            width: 16px;
            height: 16px;
            transition: transform 0.2s ease;
            flex-shrink: 0;
        }}

        .class-card:hover .icon-arrow {{
            transform: translateX(4px);
        }}

        /* Empty State */
        .empty-state {{
            grid-column: 1 / -1;
            padding: 4rem 1.5rem;
            text-align: center;
            background: #ffffff;
            border: 1px dashed var(--border-strong);
            border-radius: var(--radius-md);
            display: none;
        }}

        .empty-state.visible {{
            display: block;
        }}

        .empty-state svg {{
            width: 48px;
            height: 48px;
            color: var(--text-dim);
            margin-bottom: 1rem;
        }}

        .empty-state h3 {{
            font-size: 1.25rem;
            margin-bottom: 0.5rem;
            font-family: 'Outfit', sans-serif;
            color: #0f172a;
        }}

        .empty-state p {{
            color: var(--text-muted);
            margin-bottom: 1.5rem;
        }}

        /* Alert Banner */
        .alert-banner {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            background: #fff1f2;
            border: 1px solid #fecdd3;
            color: #be123c;
            padding: 0.85rem 1.25rem;
            border-radius: var(--radius-sm);
            margin-bottom: 1.5rem;
            font-size: 0.9rem;
        }}

        /* Footer */
        footer.site-footer {{
            margin-top: 4rem;
            padding-top: 2rem;
            border-top: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 1rem;
            font-size: 0.825rem;
            color: var(--text-dim);
        }}

        footer.site-footer a {{
            color: var(--text-muted);
            text-decoration: underline;
        }}

        footer.site-footer a:hover {{
            color: var(--accent-cyan);
        }}

        /* Responsive Breakpoints */
        @media (max-width: 640px) {{
            .container {{
                padding: 1rem 0.85rem 3rem;
            }}
            .brand-logo-wrap {{
                height: 38px;
            }}
            .brand-logo-wrap svg,
            .brand-logo-wrap img.brand-logo-img {{
                height: 30px;
                max-width: 170px;
            }}
            .brand-text h1 {{
                font-size: 1.25rem;
            }}
            .controls-panel {{
                padding: 1rem;
                gap: 1rem;
            }}
            .controls-right {{
                width: 100%;
                justify-content: space-between;
            }}
            .classes-grid {{
                grid-template-columns: 1fr;
                gap: 1rem;
            }}
            .btn-header span {{
                display: none;
            }}
        }}

        @media (min-width: 1400px) {{
            .classes-grid {{
                grid-template-columns: repeat(4, 1fr);
            }}
        }}

        @media (min-width: 1920px) {{
            .classes-grid {{
                grid-template-columns: repeat(5, 1fr);
            }}
        }}
    </style>
</head>
<body>
    <div class="page-ambient"></div>
    <div class="container">
        <header class="site-header">
            <a href="{EVENTBRITE_PROFILE_URL}" target="_blank" rel="noopener noreferrer" class="brand-block">
                {logo_html}
                <div class="brand-text">
                    <h1>Classes &amp; Workshops</h1>
                    <p>Community Maker Space &bull; Nashua, NH</p>
                </div>
            </a>
            <div class="header-actions">
                <a href="?refresh=1" class="btn-header" title="Refresh schedule from Eventbrite">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"/>
                        <polyline points="1 20 1 14 7 14"/>
                        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                    </svg>
                    <span>Refresh</span>
                </a>
                <a href="{EVENTBRITE_PROFILE_URL}" target="_blank" rel="noopener noreferrer" class="btn-header btn-header-primary">
                    <span>Eventbrite Organizer</span>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                        <polyline points="15 3 21 3 21 9"/>
                        <line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                </a>
            </div>
        </header>

        {error_banner}

        <section class="controls-panel">
            <div class="search-row">
                <div class="search-box">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="11" cy="11" r="8"/>
                        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                    </svg>
                    <input type="text" id="classSearch" placeholder="Search classes by keyword, tool, or topic (e.g. lathe, welding, laser)..." autocomplete="off">
                </div>
                <div class="controls-right">
                    <button type="button" class="btn-toggle-soldout" id="toggleSoldOutBtn" aria-pressed="false">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                            <line x1="1" y1="1" x2="23" y2="23"/>
                        </svg>
                        <span id="toggleSoldOutText">Hide Sold Out</span>
                    </button>
                    <div class="stats-badge" id="statsBadge">
                        Showing <strong id="visibleCount">{total_count}</strong> of {total_count} classes
                    </div>
                </div>
            </div>
            <div class="filter-pills" id="filterPills">
                {filter_pills_html}
            </div>
        </section>

        <main class="classes-grid" id="classesGrid">
            {cards_joined}
            <div class="empty-state" id="emptyState">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="11" cy="11" r="8"/>
                    <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
                <h3>No matching classes found</h3>
                <p>Try searching for a different keyword or resetting your category and sold-out filters.</p>
                <button type="button" class="btn-header" onclick="resetFilters()">Reset All Filters</button>
            </div>
        </main>

        <footer class="site-footer">
            <div>
                MakeIt Labs &bull; 25 Crown St, Nashua, NH 03060 &bull;
                <a href="{EVENTBRITE_PROFILE_URL}" target="_blank" rel="noopener noreferrer">View All on Eventbrite</a>
            </div>
            <div>
                Last updated: {last_updated}
            </div>
        </footer>
    </div>

    <script>
        (function() {{
            const searchInput = document.getElementById('classSearch');
            const filterPills = document.querySelectorAll('.filter-pill');
            const cards = document.querySelectorAll('.class-card');
            const visibleCountEl = document.getElementById('visibleCount');
            const statsBadge = document.getElementById('statsBadge');
            const emptyState = document.getElementById('emptyState');
            const toggleSoldOutBtn = document.getElementById('toggleSoldOutBtn');
            const toggleSoldOutText = document.getElementById('toggleSoldOutText');

            let currentCategory = 'all';
            let searchQuery = '';
            let hideSoldOut = false;
            const totalClasses = {total_count};

            function applyFilters() {{
                let visibleCount = 0;
                let hiddenSoldOutCount = 0;
                const query = searchQuery.trim().toLowerCase();

                cards.forEach(card => {{
                    const title = card.getAttribute('data-title') || '';
                    const cats = (card.getAttribute('data-cats') || '').split(' ');
                    const isSoldOut = card.getAttribute('data-soldout') === 'true';

                    const matchesSearch = !query || title.includes(query) || card.textContent.toLowerCase().includes(query);
                    const matchesCategory = currentCategory === 'all' || cats.includes(currentCategory);
                    const matchesSoldOut = !hideSoldOut || !isSoldOut;

                    if (isSoldOut && hideSoldOut && matchesSearch && matchesCategory) {{
                        hiddenSoldOutCount++;
                    }}

                    if (matchesSearch && matchesCategory && matchesSoldOut) {{
                        card.style.display = '';
                        visibleCount++;
                    }} else {{
                        card.style.display = 'none';
                    }}
                }});

                if (visibleCountEl) {{
                    visibleCountEl.textContent = visibleCount;
                }}
                if (statsBadge) {{
                    if (hideSoldOut && hiddenSoldOutCount > 0) {{
                        statsBadge.innerHTML = `Showing <strong>${{visibleCount}}</strong> of ${{totalClasses}} classes (${{hiddenSoldOutCount}} sold out hidden)`;
                    }} else {{
                        statsBadge.innerHTML = `Showing <strong>${{visibleCount}}</strong> of ${{totalClasses}} classes`;
                    }}
                }}

                if (emptyState) {{
                    if (visibleCount === 0) {{
                        emptyState.classList.add('visible');
                    }} else {{
                        emptyState.classList.remove('visible');
                    }}
                }}
            }}

            if (searchInput) {{
                searchInput.addEventListener('input', (e) => {{
                    searchQuery = e.target.value;
                    applyFilters();
                }});
            }}

            if (toggleSoldOutBtn) {{
                toggleSoldOutBtn.addEventListener('click', () => {{
                    hideSoldOut = !hideSoldOut;
                    toggleSoldOutBtn.classList.toggle('active', hideSoldOut);
                    toggleSoldOutBtn.setAttribute('aria-pressed', hideSoldOut ? 'true' : 'false');
                    if (toggleSoldOutText) {{
                        toggleSoldOutText.textContent = hideSoldOut ? 'Showing Available Only' : 'Hide Sold Out';
                    }}
                    applyFilters();
                }});
            }}

            filterPills.forEach(pill => {{
                pill.addEventListener('click', () => {{
                    filterPills.forEach(p => p.classList.remove('active'));
                    pill.classList.add('active');
                    currentCategory = pill.getAttribute('data-filter') || 'all';
                    applyFilters();
                }});
            }});

            window.resetFilters = function() {{
                if (searchInput) searchInput.value = '';
                searchQuery = '';
                currentCategory = 'all';
                hideSoldOut = false;
                if (toggleSoldOutBtn) {{
                    toggleSoldOutBtn.classList.remove('active');
                    toggleSoldOutBtn.setAttribute('aria-pressed', 'false');
                    if (toggleSoldOutText) toggleSoldOutText.textContent = 'Hide Sold Out';
                }}
                filterPills.forEach(p => {{
                    if (p.getAttribute('data-filter') === 'all') {{
                        p.classList.add('active');
                    }} else {{
                        p.classList.remove('active');
                    }}
                }});
                applyFilters();
            }};
        }})();
    </script>
</body>
</html>'''

# ---------------------------------------------------------------------------
# CGI Output Execution
# ---------------------------------------------------------------------------
def main():
    force_refresh = False
    cache_only = False
    quiet = False
    output_file = None

    for arg in sys.argv[1:]:
        if arg in ("-c", "--cache-only", "--refresh-only", "--cron", "--update-cache"):
            cache_only = True
            force_refresh = True
        elif arg in ("-r", "--refresh"):
            force_refresh = True
        elif arg in ("-q", "--quiet"):
            quiet = True
        elif arg.startswith("--output="):
            output_file = arg.split("=", 1)[1]

    query_string = os.environ.get("QUERY_STRING", "")
    if "cache_only=1" in query_string or "refresh_only=1" in query_string or "cron=1" in query_string:
        cache_only = True
        force_refresh = True
    elif "refresh=1" in query_string:
        force_refresh = True

    # Fast path for cron / background cache updates:
    # Updates cache atomically and avoids expensive HTML rendering, SVG embedding, and templating.
    if cache_only:
        try:
            classes, last_updated = fetch_events_from_eventbrite(force_refresh=True)
            if "GATEWAY_INTERFACE" in os.environ:
                print("Content-Type: text/plain; charset=utf-8\r\n\r\n", end="")
                print(f"OK: Refreshed {len(classes)} classes ({last_updated})")
            elif not quiet:
                print(f"Cache refreshed successfully: {len(classes)} classes cached ({last_updated}).")
            sys.exit(0)
        except Exception as e:
            if "GATEWAY_INTERFACE" in os.environ:
                print("Status: 500 Internal Server Error\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n", end="")
                print(f"Error refreshing cache: {e}")
            else:
                sys.stderr.write(f"Error refreshing cache: {e}\n")
            sys.exit(1)

    html = render_classes_page(force_refresh=force_refresh)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Wrote classes to {output_file}")
        return

    # Standard CGI output: Headers followed by blank line and body
    print("Content-Type: text/html; charset=utf-8\r\n\r\n", end="")
    print(html)

if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
