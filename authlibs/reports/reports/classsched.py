#!/usr/bin/python3

TOKEN = ""
with open("eventbrite.token") as fd:
    TOKEN = fd.read().strip()
import requests
import csv,sys
from datetime import datetime, timedelta

def get_super_event_grid(super_map, oauth_token):
    headers = {"Authorization": f"Bearer {oauth_token}"}

    # 1. Setup 24-month Grid
    now = datetime.now()
    month_keys = []
    start_point = (now - timedelta(days=365)).replace(day=1)
    for i in range(25):
        m_key = (start_point + timedelta(days=i*31)).strftime('%Y-%m')
        if len(month_keys) < 24: month_keys.append(m_key)

    # Flatten IDs for the API search, but keep the super_grid for storage
    all_target_ids = [str(sid) for sublist in super_map.values() for sid in sublist]
    super_grid = {name: {m: {"s": 0, "c": 0} for m in month_keys} for name in super_map.keys()}

    # 2. Get Org ID
    org_res = requests.get("https://www.eventbriteapi.com/v3/users/me/organizations/", headers=headers)
    org_id = org_res.json()['organizations'][0]['id']

    # 3. Pull all events
    url = f"https://www.eventbriteapi.com/v3/organizations/{org_id}/events/"
    params = {"status": "live,ended,completed,started", "time_filter": "all", "expand": "ticket_classes", "page_size": 100}

    has_more = True
    continuation = None
    while has_more:
        if continuation: params['continuation'] = continuation
        response = requests.get(url, headers=headers, params=params).json()

        for event in response.get('events', []):
            eid, pid = str(event.get('id')), str(event.get('primary_event_id') or event.get('series_id', "None"))

            # Find which Super-Event this specific date belongs to
            for super_name, id_list in super_map.items():
                if eid in id_list or pid in id_list:
                    m_key = event.get('start', {}).get('utc', '')[:7]
                    if m_key in super_grid[super_name]:
                        tcs = event.get('ticket_classes', [])
                        super_grid[super_name][m_key]["s"] += sum(t.get('quantity_sold', 0) for t in tcs)
                        super_grid[super_name][m_key]["c"] += event.get('capacity', 0) or sum(t.get('quantity_total', 0) for t in tcs)

        has_more = response.get('pagination', {}).get('has_more_items', False)
        continuation = response.get('pagination', {}).get('continuation')

    # 4. PRINT HTML
    html = "HTML:\n"
    html += "<style>\n"
    html += "table.classsched { border-collapse: collapse; width: 100%; font-family: sans-serif; }\n"
    html += "table.classsched th, table.classsched td { border: 1px solid #ddd; padding: 8px; text-align: center; }\n"
    html += "table.classsched th { background-color: #f2f2f2; position: sticky; top: 0; }\n"
    html += "table.classsched td:first-child { text-align: left; font-weight: bold; background-color: #f9f9f9; position: sticky; left: 0; z-index: 1; }\n"
    html += "</style>\n"
    
    html += "<div style='font-family: Arial, sans-serif; padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>\n"
    html += "<h2 style='color: #333; margin-top: 0;'>Class Schedule & Attendance Report</h2>"
    html += "<p style='color: #666; margin-bottom: 20px;'>Attendance percentage per class category.</p>"

    html += "<div style='overflow-x: auto;'>\n"
    html += "<table class='classsched'>\n"
    
    short_months = [m[5:] + "-" + m[2:4] for m in month_keys]
    html += "<tr><th>Category</th>" + "".join(f"<th>{m}</th>" for m in short_months) + "</tr>\n"
    
    current_m = datetime.now().strftime('%Y-%m')
    
    for name in super_map.keys():
        html += f"<tr><td>{name}</td>"
        for m in month_keys:
            s, c = super_grid[name][m]['s'], super_grid[name][m]['c']
            pct = s / c if c > 0 else None
            
            bg_color = "#ffffff"
            text_color = "#000000"
            text = f"{int(pct*100)}%" if pct is not None else "-"
            
            if pct is not None:
                if m < current_m:
                    # Past month
                    lightness = 90 - (pct * 50) # 90 down to 40
                    hue = 60 + (pct * 60) # 60 up to 120
                    bg_color = f"hsl({hue}, 80%, {lightness}%)"
                    if lightness < 50: text_color = "#ffffff"
                elif m == current_m:
                    # Current month
                    lightness = 95 - (pct * 65) # 95 down to 30
                    sat = 20 + (pct * 80) # 20 up to 100
                    bg_color = f"hsl(120, {sat}%, {lightness}%)"
                    if lightness < 50: text_color = "#ffffff"
                else:
                    # Future month
                    if pct >= 0.75:
                        # Scale from Green (120) to Red (0) as pct goes from 0.75 to 1.0
                        hue = 120 - ((pct - 0.75) / 0.25 * 120)
                        lightness = 40 + ((pct - 0.75) / 0.25 * 10) # 40 up to 50
                        bg_color = f"hsl({hue}, 100%, {lightness}%)"
                        if hue < 60 or lightness < 50: text_color = "#ffffff"
                    else:
                        # Scale from Yellow (60) to Green (120) as pct goes from 0.0 to 0.75
                        hue = 60 + (pct / 0.75 * 60)
                        lightness = 80 - (pct / 0.75 * 40) # 80 down to 40
                        bg_color = f"hsl({hue}, 80%, {lightness}%)"
                        if lightness < 50: text_color = "#ffffff"
            
            html += f"<td style='background-color: {bg_color}; color: {text_color};'>{text}</td>"
        html += "</tr>\n"
        
    html += "</table>\n"
    html += "</div>\n</div>\n"
    print(html)

# --- DEFINE YOUR GROUPS HERE ---
MY_MAPPINGS = {
    "Epilog": ["444283543037"], 
    "MOPA": ["1982595934811"], 
    "Wood Orientation": ["119567829597"],  
    "Wood Bandsaw": ["557157070797"],
    "Wood Lathe": ["1965258959451"],
    "Wood Projects": ["1612325150929", "1984349771584"], # Cutting board and Picture Frame
    "Blacksmithing": ["1243682861919"],
    "Waterjet": ["663602140867"],
    "Design Tools": ["632359854347", "850035929347", "850045999467","1320096898359"], #Inkscape, Bkebder, Onshape, Meetup
    "Pottery": ["678019884727", "1596586807119"], #Glazing, Intro
    "Metal Fab": ["1092937859559"], # VBandsaw
    "Soft Metals": ["1978809165482","1740582431909", "1968713594357","1982891955216", "1983318849067"], # Siver Wire Scape,< Copper Pendant, Smith & Annel, Ring Fab
    "Shopbot": ["1978640823968"],
    "Lil Tormy": ["1867525161029"],
    "Soldering": ["1703566807179"],
    "Auto": ["1981598624830"],
    "Welding": ["1982281184384","1982278329846"], # TIG, MIG
    "Machine Shop": ["1982282866415", "1982283357885"], # Lathe Mill
    "Kitchen": ["1983906519806"], # Baguettes
    "Glass": ["1982895978249"], # Stained Glass
    "Glenn": ["1982227839829", "1982220233077", "1983334369489", "1982797679234", "1983589684142"] # DriilDoctor, TOrmech, DieSub, Lapedary
}

#get_super_event_grid(MY_MAPPINGS, TOKEN)
get_super_event_grid(MY_MAPPINGS, TOKEN)
