from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, jsonify
from flask_user import current_user, login_required
from authlibs.db_models import db, Event, EventDate, EventInstructor, Member
from authlibs import utilities
import datetime
import re
import os
import json
import base64
import urllib.request
import textwrap
from dateutil import tz
from . import classes_bp

@classes_bp.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if not current_user.privs('Classes') and not current_user.privs('Admin'):
        flash("You are not authorized to view the Class Administration page.", "danger")
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        event_id = request.form.get('event_id')
        member_id = request.form.get('member_id')
        
        if action == 'assign':
            # userlist.js returns the string 'member' field (e.g. jdoe) instead of integer ID
            m = Member.query.filter_by(member=member_id).first()
            if m:
                if not EventInstructor.query.filter_by(event_id=event_id, member_id=m.id).first():
                    ei = EventInstructor(event_id=event_id, member_id=m.id)
                    db.session.add(ei)
                    db.session.commit()
                    flash("Instructor assigned", "success")
            else:
                flash("Member not found", "danger")
        elif action == 'unassign':
            ei = EventInstructor.query.filter_by(event_id=event_id, member_id=member_id).first()
            if ei:
                db.session.delete(ei)
                db.session.commit()
                flash("Instructor unassigned", "success")
        return redirect(url_for('classes.admin'))

    events = Event.query.order_by(Event.name).all()
    return render_template('class_admin.html', events=events)

from dateutil import tz

@classes_bp.route('/my_classes')
@login_required
def my_classes():
    active_view = request.args.get('view', 'by_class')
    instructor_links = EventInstructor.query.filter_by(member_id=current_user.id).all()
    event_ids = [ei.event_id for ei in instructor_links]
    
    ny_tz = tz.gettz('America/New_York')
    now = datetime.datetime.now(tz=ny_tz).replace(tzinfo=None)
    my_events = Event.query.filter(Event.id.in_(event_ids)).order_by(Event.name).all() if event_ids else []
    
    target_eventbrite_ids = set()
    chronological_dates = []
    for ev in my_events:
        for ed in ev.dates:
            if ed.time_start >= now:
                target_eventbrite_ids.add(ed.eventbrite_id)
                chronological_dates.append(ed)

    chronological_dates.sort(key=lambda d: d.time_start)
                
    from .eventbrite import get_event_capacities
    capacities = get_event_capacities(target_eventbrite_ids=target_eventbrite_ids) if target_eventbrite_ids else {}
    
    event_warnings = {}
    for ev in my_events:
        upcoming_dates = [ed for ed in ev.dates if ed.time_start >= now]
        if not upcoming_dates:
            event_warnings[ev.id] = {"text": "No upcoming classes scheduled.", "level": "secondary"}
        else:
            all_full = True
            next_avail = None
            for ed in upcoming_dates:
                cap_info = capacities.get(ed.eventbrite_id, {})
                is_full = cap_info.get('is_sold_out', False)
                if not is_full:
                    all_full = False
                    if not next_avail or ed.time_start < next_avail.time_start:
                        next_avail = ed
            
            if all_full:
                event_warnings[ev.id] = {"text": "All upcoming dates for this class are SOLD OUT", "level": "danger"}
            elif next_avail:
                event_warnings[ev.id] = {"text": f"Next available seat is on {next_avail.time_start.strftime('%b %d')}", "level": "success"}

    return render_template(
        'my_classes.html',
        events=my_events,
        chronological_dates=chronological_dates,
        capacities=capacities,
        event_warnings=event_warnings,
        now=now,
        active_view=active_view
    )

@classes_bp.route('/event/<eventbrite_id>/attendees')
@login_required
def get_event_attendees(eventbrite_id):
    from .eventbrite import get_attendees
    attendees = get_attendees(eventbrite_id)
    return jsonify({"attendees": attendees})

@classes_bp.route('/api/cron_sync')
def cron_sync():
    from .eventbrite import sync_events, notify_instructors
    success, msg = sync_events()
    if success:
        notify_instructors()
        return jsonify({"status": "ok", "message": "Synced and notifications sent"})
    else:
        return jsonify({"status": "error", "message": msg}), 500

@classes_bp.route('/api/send_notices')
@login_required
def send_notices():
    if not current_user.privs('Classes') and not current_user.privs('Admin'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    from .eventbrite import notify_instructors
    notify_instructors()
    return jsonify({"status": "ok", "message": "Notices sent"})

# ---------------------------------------------------------------------------
# Social Media Class Promo Generator
# ---------------------------------------------------------------------------
def wrap_text_lines(text, max_chars, max_lines=3):
    if not text:
        return []
    lines = textwrap.wrap(str(text).strip(), width=max_chars)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines[-1].endswith('.'):
            lines[-1] = lines[-1][:-1] + '...'
        else:
            lines[-1] = lines[-1] + '...'
    return lines

def fetch_image_as_base64(url, timeout=3):
    if not url:
        return None
    if url.startswith("data:"):
        return url
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'MakeItLabs-Promo/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get_content_type()
            data = resp.read()
            b64 = base64.b64encode(data).decode('utf-8')
            return f"data:{content_type};base64,{b64}"
    except Exception:
        return None

def get_logo_data_uri():
    for p in [
        os.path.join(current_app.root_path, "..", "static", "MakeIt Labs Logo 2016.svg"),
        os.path.join(current_app.root_path, "static", "MakeIt Labs Logo 2016.svg"),
        os.path.join(os.path.abspath('.'), "static", "MakeIt Labs Logo 2016.svg")
    ]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read()
                cleaned = re.sub(r'<foreignObject[^>]*>(?:.*?</foreignObject>)?', '', content, flags=re.DOTALL)
                b64 = base64.b64encode(cleaned.encode("utf-8")).decode("utf-8")
                return f"data:image/svg+xml;base64,{b64}"
            except Exception:
                pass
    return None

def get_logo_svg_inner():
    for p in [
        os.path.join(current_app.root_path, "..", "static", "MakeIt Labs Logo 2016.svg"),
        os.path.join(current_app.root_path, "static", "MakeIt Labs Logo 2016.svg"),
        os.path.join(os.path.abspath('.'), "static", "MakeIt Labs Logo 2016.svg")
    ]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    text = f.read()
                m = re.search(r'(<g\s+inkscape:label=\"Layer 1\".*?</g>\s*</svg>)', text, re.DOTALL)
                if m:
                    inner = m.group(1).rsplit('</svg>', 1)[0].strip()
                    inner = re.sub(r'inkscape:[a-zA-Z0-9_-]+=\"[^\"]*\"', '', inner)
                    inner = re.sub(r'sodipodi:[a-zA-Z0-9_-]+=\"[^\"]*\"', '', inner)
                    inner = re.sub(r'<foreignObject[^>]*>(?:.*?</foreignObject>)?', '', inner, flags=re.DOTALL)
                    return inner
            except Exception:
                pass
    return None

def categorize_class_promo(name):
    n = name.lower()
    if any(k in n for k in ["wood", "lathe", "shopbot", "carpentry"]):
        return "Woodworking"
    if any(k in n for k in ["weld", "metal", "machin", "mill", "trak", "bridgeport", "pewter", "plasma"]):
        return "Metal & Welding"
    if any(k in n for k in ["laser", "kern", "epilog", "mopa", "fiber", "cnc", "router", "waterjet"]):
        return "Laser & CNC"
    if any(k in n for k in ["ceramic", "glaz", "glass", "pottery", "art", "jewelry", "wire wrap", "apparel", "mat board", "ornament", "sewing", "embroidery"]):
        return "Arts & Crafts"
    if any(k in n for k in ["cad", "onshape", "blender", "inkscape", "design tools", "software", "3d print", "cura", "prusa"]):
        return "CAD & 3D Printing"
    if any(k in n for k in ["orient", "safety", "authoriz", "walkthrough", "intro", "101", "basics"]):
        return "Orientation & Safety"
    return "Workshop"

def get_promo_classes(force_refresh=False):
    # 1. Try local cache from classes.cgi if available
    cache_paths = [
        os.path.join(os.path.expanduser("~"), ".cache", "makeit_classboard_cache.json"),
        "/tmp/makeit_classboard_cache.json"
    ]
    if not force_refresh:
        for cp in cache_paths:
            if os.path.exists(cp):
                try:
                    with open(cp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        raw_classes = data.get("classes", [])
                        if raw_classes:
                            formatted = []
                            for c in raw_classes:
                                cat = c.get("categories", ["Workshop"])
                                cat_str = cat[0] if isinstance(cat, list) and cat else "Workshop"
                                if cat_str == "all":
                                    cat_str = categorize_class_promo(c.get("title", ""))
                                else:
                                    cat_str = cat_str.replace("-", " ").title()
                                formatted.append({
                                    "id": c.get("id"),
                                    "title": c.get("title", "Untitled Class"),
                                    "logo_url": c.get("logo_url"),
                                    "date_str": c.get("formatted_date", ""),
                                    "summary": c.get("summary", ""),
                                    "category": cat_str,
                                    "url": c.get("url", "")
                                })
                            return formatted
                except Exception:
                    pass

    # 2. Try Eventbrite live fetch if credentials exist
    from .eventbrite import get_eventbrite_creds
    org_id, token = get_eventbrite_creds()
    if org_id and token:
        try:
            url = f"https://www.eventbriteapi.com/v3/organizations/{org_id}/events/?status=live,started&token={token}&expand=ticket_availability,logo"
            req = urllib.request.Request(url, headers={"User-Agent": "MakeItLabs/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                events = data.get("events", [])
                
                now = datetime.datetime.now()
                now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
                groups = {}
                for e in events:
                    key = e.get("series_id") or e.get("id")
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(e)

                promo_list = []
                for k, items in groups.items():
                    upcoming = [x for x in items if x.get("start", {}).get("local", "") >= now_iso]
                    if not upcoming:
                        continue
                    upcoming.sort(key=lambda x: x.get("start", {}).get("local", ""))
                    next_item = upcoming[0]

                    title = next_item.get("name", {}).get("text", "Untitled Workshop").strip()
                    logo_url = None
                    if next_item.get("logo"):
                        logo_obj = next_item["logo"]
                        logo_url = logo_obj.get("original", {}).get("url") or logo_obj.get("url")

                    summary = next_item.get("summary") or ""
                    if not summary and next_item.get("description", {}).get("text"):
                        summary = next_item["description"]["text"][:140].strip() + "..."

                    start_str = next_item.get("start", {}).get("local", "")
                    try:
                        next_dt = datetime.datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S")
                        date_str = next_dt.strftime("%a, %b %d • %I:%M %p").replace(" 0", " ")
                    except Exception:
                        date_str = start_str

                    series_id = next_item.get("series_id")
                    item_url = next_item.get("url", "")
                    if series_id:
                        if "tickets-" in item_url:
                            item_url = re.sub(r"tickets-\d+", f"tickets-{series_id}", item_url)
                        else:
                            item_url = f"https://www.eventbrite.com/e/{series_id}"
                    if item_url.startswith("http://"):
                        item_url = "https://" + item_url[7:]
                    if logo_url and logo_url.startswith("http://"):
                        logo_url = "https://" + logo_url[7:]

                    promo_list.append({
                        "id": next_item.get("id"),
                        "title": title,
                        "logo_url": logo_url,
                        "date_str": date_str,
                        "summary": summary,
                        "category": categorize_class_promo(title),
                        "url": item_url
                    })
                if promo_list:
                    return promo_list
        except Exception as ex:
            print(f"Eventbrite fetch error for promo: {ex}")

    # 3. Fallback to database models (Event & EventDate)
    ny_tz = tz.gettz('America/New_York')
    now = datetime.datetime.now(tz=ny_tz).replace(tzinfo=None)
    db_events = Event.query.all()
    fallback_list = []
    for ev in db_events:
        dates = [d for d in ev.dates if d.time_start and d.time_start >= now]
        if not dates:
            continue
        dates.sort(key=lambda d: d.time_start)
        next_d = dates[0]
        date_str = next_d.time_start.strftime("%a, %b %d • %I:%M %p").replace(" 0", " ")
        summary = (ev.description or "")[:140]
        if len(ev.description or "") > 140:
            summary += "..."
        fallback_list.append({
            "id": ev.id,
            "title": ev.name,
            "logo_url": None,
            "date_str": date_str,
            "summary": summary,
            "category": categorize_class_promo(ev.name),
            "url": ev.url or ""
        })
    return fallback_list

@classes_bp.route('/social_promo', methods=['GET'])
@login_required
def social_promo():
    force_refresh = request.args.get('refresh') == '1'
    classes = get_promo_classes(force_refresh=force_refresh)
    return render_template('social_promo_form.html', classes=classes)

@classes_bp.route('/social_promo/generate', methods=['POST'])
@login_required
def social_promo_generate():
    selected_indices = request.form.getlist('selected_indices')
    if not selected_indices:
        selected_indices = [k.replace('include_', '') for k in request.form.keys() if k.startswith('include_')]

    try:
        indices = sorted([int(i) for i in selected_indices if str(i).isdigit()])
    except Exception:
        indices = []

    if not indices:
        flash("No classes were selected. Please select 1 to 4 classes to generate a promo graphic.", "warning")
        return redirect(url_for('classes.social_promo'))

    if len(indices) > 4:
        indices = indices[:4]

    headline = request.form.get('headline', 'UPCOMING WORKSHOPS & CLASSES').strip()
    subhead = request.form.get('subhead', 'Hands-on Making • Open to the Public • Nashua, NH').strip()
    aspect_ratio = request.form.get('aspect_ratio', 'portrait')

    svg_width = 1080
    svg_height = 1080 if aspect_ratio == 'square' else 1350

    events = []
    for idx in indices:
        title = request.form.get(f'title_{idx}', '').strip()
        date_str = request.form.get(f'date_{idx}', '').strip()
        category = request.form.get(f'category_{idx}', '').strip()
        summary = request.form.get(f'summary_{idx}', '').strip()
        image_url = request.form.get(f'image_url_{idx}', '').strip()

        img_b64 = fetch_image_as_base64(image_url) if image_url else None

        events.append({
            'title': title,
            'date_str': date_str,
            'category': category,
            'summary': summary,
            'image_data_uri': img_b64
        })

    num_events = len(events)
    for i, e in enumerate(events):
        if num_events == 2:
            card_y = 240 + i * 505
            e['clip_x'] = 65
            e['clip_y'] = card_y + 25
            e['clip_w'] = 425
            e['clip_h'] = 425
            e['clip_rx'] = 16
            e['title_lines'] = wrap_text_lines(e['title'], max_chars=25, max_lines=3)
            e['summary_lines'] = wrap_text_lines(e['summary'], max_chars=40, max_lines=3)
            e['cat_pill_w'] = max(110, len(e.get('category', '')) * 11 + 24)
        elif num_events == 3:
            card_y = 236 + i * 338
            e['clip_x'] = 60
            e['clip_y'] = card_y + 20
            e['clip_w'] = 380
            e['clip_h'] = 278
            e['clip_rx'] = 14
            e['title_lines'] = wrap_text_lines(e['title'], max_chars=34, max_lines=2)
            e['summary_lines'] = wrap_text_lines(e['summary'], max_chars=48, max_lines=3)
            e['cat_pill_w'] = max(100, len(e.get('category', '')) * 10 + 20)
        elif num_events == 4:
            col = i % 2
            row = i // 2
            card_x = 40 + col * 515
            card_y = 236 + row * 515
            e['clip_x'] = card_x + 15
            e['clip_y'] = card_y + 15
            e['clip_w'] = 455
            e['clip_h'] = 235
            e['clip_rx'] = 12
            e['title_lines'] = wrap_text_lines(e['title'], max_chars=28, max_lines=2)
            e['summary_lines'] = wrap_text_lines(e['summary'], max_chars=38, max_lines=2)
            e['cat_pill_w'] = max(90, len(e.get('category', '')) * 10 + 26)
        else: # 1 hero
            e['clip_x'] = 65
            e['clip_y'] = 265
            e['clip_w'] = 950
            e['clip_h'] = 520
            e['clip_rx'] = 16
            e['title_lines'] = wrap_text_lines(e['title'], max_chars=45, max_lines=2)
            e['summary_lines'] = wrap_text_lines(e['summary'], max_chars=65, max_lines=3)
            e['cat_pill_w'] = max(120, len(e.get('category', '')) * 12 + 24)

    logo_data_uri = get_logo_data_uri()
    logo_svg_inner = get_logo_svg_inner()
    footer_text = "MAKEITLABS.COM • 25 CROWN ST, NASHUA, NH • DETAILS AT MAKEITLABS.COM"

    svg = render_template(
        'social_promo_svg.xml',
        events=events,
        headline=headline,
        subhead=subhead,
        footer_text=footer_text,
        svg_width=svg_width,
        svg_height=svg_height,
        logo_data_uri=logo_data_uri,
        logo_svg_inner=logo_svg_inner
    )

    return render_template('social_promo_result.html', svg=svg)

def register_pages(app):
    app.register_blueprint(classes_bp, url_prefix='/classes')
