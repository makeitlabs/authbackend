import requests
import datetime
from dateutil import tz
from flask import current_app
from authlibs.db_models import db, Event, EventDate, EventInstructor
from authlibs.google_admin import genericEmailSender

import os

def get_eventbrite_creds():
    org_id = ""
    token = ""
    if 'globalConfig' in current_app.config and hasattr(current_app.config['globalConfig'], 'Config'):
        org_id = current_app.config['globalConfig'].Config.get('Eventbrite', 'org_id', fallback='')
        token = current_app.config['globalConfig'].Config.get('Eventbrite', 'token', fallback='')
    if not token or not org_id:
        try:
            import cgimisc.vars as config_vars
            if hasattr(config_vars, 'ORG_ID') and config_vars.ORG_ID:
                org_id = config_vars.ORG_ID
            if hasattr(config_vars, 'TOKEN') and config_vars.TOKEN:
                token = config_vars.TOKEN
        except Exception:
            try:
                import vars as config_vars
                if hasattr(config_vars, 'ORG_ID') and config_vars.ORG_ID:
                    org_id = config_vars.ORG_ID
                if hasattr(config_vars, 'TOKEN') and config_vars.TOKEN:
                    token = config_vars.TOKEN
            except Exception:
                pass
    if not token:
        token = os.environ.get("EVENTBRITE_TOKEN") or os.environ.get("TOKEN") or ""
    if not org_id:
        org_id = os.environ.get("EVENTBRITE_ORG_ID") or "27283320655"
    return org_id, token

def sync_events():
    org_id, token = get_eventbrite_creds()
    if not org_id or not token:
        return False, "Missing Eventbrite configuration"
    
    # Fetch live events
    # The API returns every instance (with dates) directly in the feed.
    # Series instances have a series_id field — we group them under one Event using that.
    # Series parent objects are NOT returned by this endpoint.
    url = f"https://www.eventbriteapi.com/v3/organizations/{org_id}/events/?status=live&token={token}"
    
    active_inst_ids = set()

    try:
        has_more = True
        while has_more and url:
            r = requests.get(url)
            if r.status_code != 200:
                return False, f"Error fetching events: {r.status_code} {r.text}"
            
            j = r.json()
            
            for e in j.get('events', []):
                # Group series instances under one Event using series_id
                parent_id = e.get('series_id')
                if parent_id:
                    eventbrite_id = parent_id
                else:
                    eventbrite_id = e['id']
                
                name = clean_str(e.get('name', {}).get('text', 'Unknown'))
                description = clean_str(e.get('description', {}).get('text', '')[:2000]) if e.get('description') else ''
                url_str = e.get('url', '')
                status = e.get('status', 'live')
                
                # Create or update the Event (one per class/series)
                event = Event.query.filter_by(eventbrite_id=eventbrite_id).first()
                if not event:
                    event = Event(eventbrite_id=eventbrite_id, name=name, description=description, url=url_str, status=status)
                    db.session.add(event)
                    db.session.commit()
                else:
                    event.name = name
                    event.description = description
                    event.url = url_str
                    event.status = status
                    db.session.commit()

                # Every item in the feed has a date — save it as an EventDate
                inst_id = e['id']
                active_inst_ids.add(inst_id)
                time_start_str = e.get('start', {}).get('local')
                time_end_str = e.get('end', {}).get('local')
                
                if time_start_str and time_end_str:
                    time_start = datetime.datetime.strptime(time_start_str, "%Y-%m-%dT%H:%M:%S")
                    time_end = datetime.datetime.strptime(time_end_str, "%Y-%m-%dT%H:%M:%S")
                    
                    ed = EventDate.query.filter_by(eventbrite_id=inst_id).first()
                    if not ed:
                        ed = EventDate(event_id=event.id, eventbrite_id=inst_id, time_start=time_start, time_end=time_end)
                        db.session.add(ed)
                    else:
                        ed.time_start = time_start
                        ed.time_end = time_end
                        ed.event_id = event.id
                    db.session.commit()

            # Pagination
            pagination = j.get('pagination', {})
            has_more = pagination.get('has_more_items', False)
            if has_more:
                page = pagination.get('page_number', 1)
                url = f"https://www.eventbriteapi.com/v3/organizations/{org_id}/events/?status=live&token={token}&page={page+1}"
            else:
                url = None

        # Clean up stale EventDate records that are no longer in Eventbrite's live feed
        if active_inst_ids:
            stale_dates = EventDate.query.filter(~EventDate.eventbrite_id.in_(active_inst_ids)).all()
            for sd in stale_dates:
                db.session.delete(sd)
            db.session.commit()

    except Exception as ex:
        return False, str(ex)
    
    return True, "Synced successfully"

def get_event_capacities(target_eventbrite_ids=None):
    """
    Returns a dictionary of EventDate eventbrite_ids to their ticket availability status
    {
       '1234567': {'is_sold_out': True, 'has_available': False, 'capacity': 10, 'sold': 8}
    }
    """
    org_id, token = get_eventbrite_creds()
    if not org_id or not token:
        return {}
        
    capacities = {}
    if target_eventbrite_ids is not None:
        target_eventbrite_ids = set(target_eventbrite_ids)

    try:
        url = f"https://www.eventbriteapi.com/v3/organizations/{org_id}/events/?status=live&expand=ticket_availability&token={token}"
        
        has_more = True
        while has_more and url:
            r = requests.get(url)
            if r.status_code != 200:
                print(f"Error fetching capacities: {r.status_code} {r.text}")
                return capacities
                
            j = r.json()
            for e in j.get('events', []):
                ta = e.get('ticket_availability', {})
                capacities[e['id']] = {
                    'is_sold_out': ta.get('is_sold_out', False),
                    'has_available': ta.get('has_available_tickets', True),
                    'capacity': e.get('capacity', 0) or 0,
                    'sold': 0
                }

            pagination = j.get('pagination', {})
            has_more = pagination.get('has_more_items', False)
            if has_more:
                page = pagination.get('page_number', 1)
                url = f"https://www.eventbriteapi.com/v3/organizations/{org_id}/events/?status=live&expand=ticket_availability&token={token}&page={page+1}"
            else:
                url = None
                
        # Now fetch actual capacity numbers from ticket_classes for target events only
        for event_id in list(capacities.keys()):
            if target_eventbrite_ids is not None and event_id not in target_eventbrite_ids:
                continue
            try:
                tc_r = requests.get(f"https://www.eventbriteapi.com/v3/events/{event_id}/ticket_classes/?token={token}")
                if tc_r.status_code == 200:
                    tc_data = tc_r.json()
                    tc_capacity = 0
                    total_sold = 0
                    for tc in tc_data.get('ticket_classes', []):
                        tc_capacity += tc.get('quantity_total', 0) or 0
                        total_sold += tc.get('quantity_sold', 0) or 0
                    
                    event_cap = capacities[event_id]['capacity']
                    if event_cap > 0 and tc_capacity > 0:
                        final_cap = min(event_cap, tc_capacity)
                    elif event_cap > 0:
                        final_cap = event_cap
                    else:
                        final_cap = tc_capacity

                    capacities[event_id]['capacity'] = final_cap
                    capacities[event_id]['sold'] = total_sold
            except Exception:
                pass  # Keep the boolean-only data if ticket_classes fails
                
    except Exception as ex:
        print(f"Error fetching capacities: {ex}")
        
    return capacities

import re

def clean_str(val):
    if val is None:
        return ''
    if isinstance(val, bytes):
        try:
            val = val.decode('utf-8', errors='ignore')
        except Exception:
            val = str(val)
    else:
        val = str(val)
    
    val = val.strip()
    val = re.sub(r"\bb'([^']*)'", r"\1", val)
    val = re.sub(r'\bb"([^"]*)"', r"\1", val)
    if (val.startswith("b'") and val.endswith("'")) or (val.startswith('b"') and val.endswith('"')):
        val = val[2:-1].strip()
    return val

def get_attendees(eventbrite_id):
    org_id, token = get_eventbrite_creds()
    if not token:
        return []
    
    url = f"https://www.eventbriteapi.com/v3/events/{eventbrite_id}/attendees/?token={token}"
    attendees = []
    try:
        has_more = True
        while has_more and url:
            r = requests.get(url)
            if r.status_code != 200:
                print(f"ATTENDEES_DEBUG: status={r.status_code} body={r.text[:500]}")
                break
            data = r.json()
            for a in data.get('attendees', []):
                if a.get('cancelled') or a.get('status') == 'attending_cancelled':
                    continue
                profile = a.get('profile', {})
                first = clean_str(profile.get('first_name'))
                last = clean_str(profile.get('last_name'))
                name = clean_str(profile.get('name'))
                
                if first or last:
                    full_name = f"{first} {last}".strip()
                elif name:
                    full_name = name
                else:
                    full_name = 'Unknown'

                email = clean_str(profile.get('email')) or 'Unknown'

                attendees.append({
                    'name': full_name,
                    'email': email
                })
            pagination = data.get('pagination', {})
            has_more = pagination.get('has_more_items', False)
            if has_more:
                page = pagination.get('page_number', 1)
                url = f"https://www.eventbriteapi.com/v3/events/{eventbrite_id}/attendees/?token={token}&page={page+1}"
            else:
                url = None
    except Exception as e:
        print(f"Error fetching attendees: {e}")
    return attendees

def notify_instructors():
    # Find all EventDates starting in the next 48 hours using local US/Eastern timezone
    ny_tz = tz.gettz('America/New_York')
    now = datetime.datetime.now(tz=ny_tz).replace(tzinfo=None)
    cutoff = now + datetime.timedelta(hours=48)
    
    upcoming_dates = EventDate.query.filter(EventDate.time_start > now, EventDate.time_start <= cutoff).all()
    if not upcoming_dates:
        return
        
    target_ids = set(ed.eventbrite_id for ed in upcoming_dates)
    capacities = get_event_capacities(target_eventbrite_ids=target_ids)
    
    for ed in upcoming_dates:
        event = ed.event
        attendees = get_attendees(ed.eventbrite_id)
        
        # Calculate dynamic date relative to local today
        if ed.time_start.date() == now.date():
            day_str = "TODAY"
            when_str = "today"
        elif ed.time_start.date() == (now + datetime.timedelta(days=1)).date():
            day_str = "TOMORROW"
            when_str = "tomorrow"
        else:
            day_str = f"on {ed.time_start.strftime('%A, %b %d')}"
            when_str = f"on {ed.time_start.strftime('%A, %b %d')}"

        # 1. Send Individual Student Reminders
        if attendees:
            student_subject = f"Reminder: {event.name} {day_str}"
            for student in attendees:
                st_email = student.get('email')
                st_name = student.get('name', 'Student')
                if not st_email or st_email == 'Unknown':
                    continue
                
                st_body = f"Hello {st_name},\n\n"
                st_body += f"This is a reminder for your upcoming class at MakeIt Labs {when_str}:\n\n"
                st_body += f"Class: {event.name}\n"
                st_body += f"Date/Time: {ed.time_start.strftime('%A, %B %d, %Y at %I:%M %p')}\n"
                if event.url:
                    st_body += f"Event Link: {event.url}\n"
                st_body += "\nLocation:\nMakeIt Labs\n24 Crown St, Nashua, NH 03060\n\n"
                st_body += "We look forward to seeing you there!\n\n"
                st_body += "Thank you,\nMakeIt Labs Automation"

                try:
                    genericEmailSender("info@makeitlabs.com", st_email, student_subject, st_body)
                except Exception as e:
                    print(f"Error sending student reminder to {st_email}: {e}")

        # 2. Send Instructor Reminders (with roster & capacity)
        instructors = event.instructors.all()
        if not instructors:
            continue

        cap_info = capacities.get(ed.eventbrite_id, {})
        status_str = "Status Unknown"
        if cap_info:
            sold = cap_info.get('sold', 0)
            cap = cap_info.get('capacity', 0)
            is_sold_out = cap_info.get('is_sold_out') or (cap > 0 and sold >= cap)
            if is_sold_out:
                if cap > 0:
                    status_str = f"SOLD OUT ({sold} / {cap} Sold)"
                else:
                    status_str = "SOLD OUT"
            else:
                if cap > 0:
                    status_str = f"{sold} / {cap} Sold"
                else:
                    status_str = "Available"

        for instructor in instructors:
            member = instructor.member
            
            subject = f"Upcoming Class: {event.name} {day_str}"
            body = f"Hello {member.firstname},\n\n"
            body += f"You are scheduled to instruct the following class {when_str}:\n\n"
            body += f"Class: {event.name}\n"
            body += f"Date/Time: {ed.time_start.strftime('%A, %B %d, %Y at %I:%M %p')}\n"
            body += f"Capacity: {status_str}\n\n"
            
            if attendees:
                body += f"Registered Students ({len(attendees)}):\n"
                for a in attendees:
                    body += f"- {a['name']} ({a['email']})\n"
            else:
                body += "No students registered yet.\n"
                
            body += "\nThank you!\nMakeIt Labs Automation"
            
            # Collect both primary email and alt_email
            recipients = []
            if member.email and member.email.strip():
                recipients.append(member.email.strip())
            if member.alt_email and member.alt_email.strip():
                alt = member.alt_email.strip()
                if alt.lower() not in [r.lower() for r in recipients]:
                    recipients.append(alt)

            for recipient in recipients:
                try:
                    genericEmailSender("info@makeitlabs.com", recipient, subject, body)
                except Exception as e:
                    print(f"Error sending email to {recipient}: {e}")

