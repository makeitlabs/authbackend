#!/usr/bin/python3

import os
import re

# Categories from signup.py for friendly names
where_names = { 'holidaystroll':"Nashua Holiday Stroll", 'lksr':"Lowell Kinetic Sculpture Race", 'makeitfest':"MakeIt Fest", 'member':"From another Member", 'social':"Social Media" }
what_names = { 'art':"Art", 'blacksmithing':"Blacksmithing", 'jewelry':"Jewelry", 'glasswork':"Glasswork", 'photography':"Photography", 'pottery':"Pottery", 'woodworking':"Woodworking", 'auto':"Automotive", 'welding':"Welding", 'machining':"Machining", 'laser':"Laser Cutting", 'ham':"Ham Radio", 'production':"Production", '3dprinting':"3D Printing", 'design':"CAD/Design", 'software':"Software", 'electronics':"Electronics" }
stuff_names = { 'learning':"Taking Classes", 'community':"Community", 'collaberation':"Collaboration", 'volunteer':"Volunteering", 'making':"Making stuff", 'fixing':"Fixing stuff", 'teaching':"Teaching" }
iam_names = { 'engineer':"Engineer", 'artist':"Artist", 'hacker':"Hacker", 'teacher':"Teacher", 'student':"Student", 'builder':"Builder", 'fixer':"Fixer", 'handson':"Hands-On", 'madscientist':"Mad Scientist", 'othercientist':"Other Scientist" }

# Data stores
counts = { 'where': {}, 'what': {}, 'stuff': {}, 'iam': {} }
others = { 'where': [], 'what': [], 'stuff': [], 'iam': [] }

survey_file = "../../../survey.txt"

if not os.path.exists(survey_file):
    print("HTML:<div style='padding:20px; font-size:18px;'>No survey data found. File not found: survey.txt</div>")
    exit(0)

since_date_str = os.environ.get('REPORT_SINCE', '')

with open(survey_file, "r") as f:
    for line in f:
        # Extract predefined tokens
        tokens = line.split()
        if not tokens:
            continue
            
        timestamp_str = tokens[0].rstrip(":")
        if since_date_str:
            try:
                # Compare as strings since ISO formats match alphabetically
                if timestamp_str < since_date_str:
                    continue
            except:
                pass

        for t in tokens:
            if t.startswith('where_') and not t.startswith('other_'):
                key = t[6:]
                counts['where'][key] = counts['where'].get(key, 0) + 1
            elif t.startswith('what_') and not t.startswith('other_'):
                key = t[5:]
                counts['what'][key] = counts['what'].get(key, 0) + 1
            elif t.startswith('stuff_') and not t.startswith('other_'):
                key = t[6:]
                counts['stuff'][key] = counts['stuff'].get(key, 0) + 1
            elif t.startswith('iam_') and not t.startswith('other_'):
                key = t[4:]
                counts['iam'][key] = counts['iam'].get(key, 0) + 1
                
        # Extract 'other' strings e.g. other_where: "some_string"
        for cat in ['where', 'what', 'stuff', 'iam']:
            match = re.search(f'other_{cat}:\\s*"([^"]+)"', line)
            if match:
                val = match.group(1).replace("_", " ").strip()
                if val:
                    others[cat].append(val)

def generate_svg_chart(data, name_map, title):
    if not data:
        return f"<h4>{title}</h4><p>No data</p>"
        
    sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)
    max_val = max(data.values()) if data else 1
    
    # SVG Dimensions
    row_height = 30
    label_width = 180
    bar_max_width = 400
    svg_height = len(sorted_data) * row_height + 20
    
    html = f"<div style='margin-bottom: 30px;'>"
    html += f"<h4 style='border-bottom: 1px solid #ccc; padding-bottom: 5px;'>{title}</h4>"
    html += f"<svg width='{label_width + bar_max_width + 50}' height='{svg_height}' style='font-family: sans-serif;'>"
    
    for i, (key, count) in enumerate(sorted_data):
        y = i * row_height + 20
        friendly_name = name_map.get(key, key.capitalize())
        bar_width = max((count / max_val) * bar_max_width, 5)  # min 5px width
        
        # Label
        html += f"<text x='{label_width - 10}' y='{y + 15}' text-anchor='end' fill='#333' font-size='14px'>{friendly_name}</text>"
        # Bar
        html += f"<rect x='{label_width}' y='{y}' width='{bar_width}' height='20' fill='#0d6efd' rx='3'></rect>"
        # Count text
        html += f"<text x='{label_width + bar_width + 10}' y='{y + 15}' fill='#555' font-size='14px' font-weight='bold'>{count}</text>"
        
    html += "</svg></div>"
    return html

def generate_others_list(items, title):
    if not items:
        return ""
    html = f"<div style='margin-bottom: 30px;'>"
    html += f"<h5 style='color: #666;'>Other responses for {title}:</h5>"
    html += "<ul style='list-style-type: disc; padding-left: 20px;'>"
    for item in items:
        html += f"<li>{item}</li>"
    html += "</ul></div>"
    return html

output = "HTML:"
output += "<div style='font-family: Arial, sans-serif; padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>"
output += "<h2 style='color: #333; margin-top: 0;'>New Member Survey Report</h2>"
output += "<p style='color: #666; margin-bottom: 30px;'>Aggregated results from member signup surveys.</p>"

output += "<div style='display: flex; flex-wrap: wrap; gap: 40px;'>"
output += "<div>"
output += generate_svg_chart(counts['where'], where_names, "Where did you hear about us?")
output += generate_others_list(others['where'], 'where')
output += "</div>"

output += "<div>"
output += generate_svg_chart(counts['what'], what_names, "What are you interested in?")
output += generate_others_list(others['what'], 'what')
output += "</div>"

output += "<div>"
output += generate_svg_chart(counts['stuff'], stuff_names, "What do you want to do here?")
output += generate_others_list(others['stuff'], 'stuff')
output += "</div>"

output += "<div>"
output += generate_svg_chart(counts['iam'], iam_names, "How do you describe yourself?")
output += generate_others_list(others['iam'], 'who are you')
output += "</div>"
output += "</div>"

output += "</div>"

print(output)
