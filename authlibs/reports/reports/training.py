#!/usr/bin/python3
"""
training.py - Resource Training & Unique Usage Report (Year-over-Year)

Queries:
  - Trained members per resource per year (event_type 4000 Access Granted)
  - Unique users per resource per year (event_type 3013 Tool Login or 1025 Member Entry)

Produces combined year-over-year bar charts with numbers for each resource,
summary KPI metrics, live search/filtering/sorting, and a detailed cross-tab summary table.
"""

import os
import sys
import sqlite3
import math
from datetime import datetime
from html import escape

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DB = os.path.abspath(os.path.join(SCRIPT_DIR, "../../../log.db"))
MAKEIT_DB = os.path.abspath(os.path.join(SCRIPT_DIR, "../../../makeit.db"))

EVENT_TOOL_LOGIN = 3013
EVENT_ENTRY_ALLOWED = 1025
EVENT_ACCESS_GRANTED = 4000


def get_scale_ceiling(max_val):
    """Calculates a clean upper limit for the Y-axis so bars have room for labels."""
    if max_val <= 0:
        return 5
    elif max_val <= 5:
        return 5
    elif max_val <= 10:
        return 10
    elif max_val <= 25:
        return 25
    elif max_val <= 50:
        return 50
    elif max_val <= 100:
        return 100
    elif max_val <= 200:
        return 200
    else:
        return int(math.ceil(max_val * 1.15 / 50.0) * 50)


def generate_combined_bar_chart(res_id, res_name, years, usage_counts, training_counts, current_year_str):
    """Generates a responsive SVG bar chart with dual bars (Usage & Training) for each year."""
    max_u = max(usage_counts.values()) if usage_counts else 0
    max_t = max(training_counts.values()) if training_counts else 0
    max_val = max(max_u, max_t)
    scale_ceiling = get_scale_ceiling(max_val)

    svg_w = 520
    svg_h = 220
    pad_top = 28
    pad_bottom = 30
    pad_left = 38
    pad_right = 14

    chart_w = svg_w - pad_left - pad_right
    chart_h = svg_h - pad_top - pad_bottom
    baseline_y = pad_top + chart_h

    num_years = len(years) if years else 1
    col_w = chart_w / float(num_years)

    # 2 bars per year (Usage and Training)
    bar_w = min(18.0, max(10.0, (col_w - 8) / 2.0))
    bar_gap = 2.0

    svg = []
    svg.append(f'<svg viewBox="0 0 {svg_w} {svg_h}" width="100%" height="{svg_h}" style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; display: block; overflow: visible;">')

    grad_u = f"grad_u_{res_id}"
    grad_t = f"grad_t_{res_id}"
    svg.append(f'''<defs>
      <linearGradient id="{grad_u}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#3b82f6"/>
        <stop offset="100%" stop-color="#1d4ed8"/>
      </linearGradient>
      <linearGradient id="{grad_t}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#10b981"/>
        <stop offset="100%" stop-color="#047857"/>
      </linearGradient>
    </defs>''')

    mid_val = scale_ceiling / 2.0
    mid_y = baseline_y - chart_h / 2.0

    # Top dashed line and label
    svg.append(f'<line x1="{pad_left}" y1="{pad_top}" x2="{svg_w - pad_right}" y2="{pad_top}" stroke="#e2e8f0" stroke-dasharray="3,3" stroke-width="1"/>')
    svg.append(f'<text x="{pad_left - 6}" y="{pad_top + 4}" font-size="10px" fill="#94a3b8" text-anchor="end">{scale_ceiling}</text>')

    # Mid dashed line and label
    svg.append(f'<line x1="{pad_left}" y1="{mid_y}" x2="{svg_w - pad_right}" y2="{mid_y}" stroke="#e2e8f0" stroke-dasharray="3,3" stroke-width="1"/>')
    svg.append(f'<text x="{pad_left - 6}" y="{mid_y + 4}" font-size="10px" fill="#94a3b8" text-anchor="end">{int(mid_val)}</text>')

    # Baseline solid line and zero label
    svg.append(f'<line x1="{pad_left}" y1="{baseline_y}" x2="{svg_w - pad_right}" y2="{baseline_y}" stroke="#cbd5e1" stroke-width="1.5"/>')
    svg.append(f'<text x="{pad_left - 6}" y="{baseline_y + 3}" font-size="10px" fill="#94a3b8" text-anchor="end">0</text>')

    # Bars and data numbers for each year
    for i, yr in enumerate(years):
        center_x = pad_left + i * col_w + col_w / 2.0
        u_cnt = usage_counts.get(yr, 0)
        t_cnt = training_counts.get(yr, 0)

        # Bar 1: Usage (Left, Blue)
        x_u = center_x - bar_w - bar_gap / 2.0
        if u_cnt > 0:
            h_u = (u_cnt / float(scale_ceiling)) * chart_h
            y_u = baseline_y - h_u
            svg.append(f'<rect class="series-usage" x="{x_u:.1f}" y="{y_u:.1f}" width="{bar_w:.1f}" height="{h_u:.1f}" rx="2" ry="2" fill="url(#{grad_u})">')
            svg.append(f'<title>{escape(res_name)} - {yr}: {u_cnt} unique active users</title></rect>')
            svg.append(f'<text class="series-usage" x="{x_u + bar_w/2.0:.1f}" y="{y_u - 5:.1f}" font-size="10.5px" font-weight="600" fill="#1d4ed8" text-anchor="middle">{u_cnt}</text>')
        else:
            svg.append(f'<rect class="series-usage" x="{x_u:.1f}" y="{baseline_y - 2}" width="{bar_w:.1f}" height="2" fill="#e2e8f0"/>')
            svg.append(f'<text class="series-usage" x="{x_u + bar_w/2.0:.1f}" y="{baseline_y - 5}" font-size="9px" fill="#cbd5e1" text-anchor="middle">0</text>')

        # Bar 2: Training (Right, Green)
        x_t = center_x + bar_gap / 2.0
        if t_cnt > 0:
            h_t = (t_cnt / float(scale_ceiling)) * chart_h
            y_t = baseline_y - h_t
            svg.append(f'<rect class="series-training" x="{x_t:.1f}" y="{y_t:.1f}" width="{bar_w:.1f}" height="{h_t:.1f}" rx="2" ry="2" fill="url(#{grad_t})">')
            svg.append(f'<title>{escape(res_name)} - {yr}: {t_cnt} members trained</title></rect>')
            svg.append(f'<text class="series-training" x="{x_t + bar_w/2.0:.1f}" y="{y_t - 5:.1f}" font-size="10.5px" font-weight="600" fill="#047857" text-anchor="middle">{t_cnt}</text>')
        else:
            svg.append(f'<rect class="series-training" x="{x_t:.1f}" y="{baseline_y - 2}" width="{bar_w:.1f}" height="2" fill="#e2e8f0"/>')
            svg.append(f'<text class="series-training" x="{x_t + bar_w/2.0:.1f}" y="{baseline_y - 5}" font-size="9px" fill="#cbd5e1" text-anchor="middle">0</text>')

        # Year label below baseline
        yr_label = yr
        if yr == current_year_str:
            yr_label += "*"
        svg.append(f'<text x="{center_x:.1f}" y="{baseline_y + 17}" font-size="11px" font-weight="500" fill="#475569" text-anchor="middle">{yr_label}</text>')

    svg.append('</svg>')
    return "".join(svg)


def render_report_html(data, report_title="Resource Training & Usage Trends"):
    """Renders the combined HTML report with grouped bar charts and matrix table."""
    current_year_str = str(datetime.now().year)

    # Determine year range across all resources
    all_years_set = set()
    for res_id, info in data.items():
        all_years_set.update(info['usage'].keys())
        all_years_set.update(info['training'].keys())

    if not all_years_set:
        all_years = [current_year_str]
    else:
        min_yr = int(min(all_years_set))
        max_yr = int(max(all_years_set))
        all_years = [str(y) for y in range(min_yr, max_yr + 1)]

    # Compute KPI totals
    total_usage_all = 0
    total_training_all = 0
    year_usage_totals = {yr: 0 for yr in all_years}
    year_training_totals = {yr: 0 for yr in all_years}
    top_training_res_name = "None"
    top_training_res_val = 0

    for res_id, info in data.items():
        u_sum = sum(info['usage'].values())
        t_sum = sum(info['training'].values())
        total_usage_all += u_sum
        total_training_all += t_sum
        if t_sum > top_training_res_val:
            top_training_res_val = t_sum
            top_training_res_name = info['name']
        for yr in all_years:
            year_usage_totals[yr] += info['usage'].get(yr, 0)
            year_training_totals[yr] += info['training'].get(yr, 0)

    busiest_t_year = max(year_training_totals.items(), key=lambda x: x[1]) if year_training_totals else ("-", 0)

    html = []
    html.append("HTML:\n</pre>")
    html.append("<div style='font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif; padding: 24px; background-color: #f8fafc; border-radius: 10px; color: #1e293b;'>")

    # Header
    html.append("<div style='display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 15px; margin-bottom: 24px;'>")
    html.append("<div>")
    html.append(f"<h2 style='color: #0f172a; margin: 0 0 6px 0; font-size: 24px; font-weight: 700;'>{escape(report_title)}</h2>")
    html.append(f"<p style='color: #64748b; margin: 0; font-size: 14px;'>Year-over-year comparison of Training Authorizations (Event 4000) and Unique Active Users (Events 3013/1025) across {len(all_years)} years ({all_years[0]} - {all_years[-1]})</p>")
    if current_year_str in all_years:
        html.append(f"<p style='color: #0369a1; margin: 4px 0 0 0; font-size: 12px; font-weight: 500;'>* Note: {current_year_str} reflects Year-to-Date (YTD) numbers.</p>")
    html.append("</div>")
    html.append("</div>")

    # KPI Metric Cards
    html.append("<div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px;'>")
    kpis = [
        ("Total Trainings Granted", f"{total_training_all:,}", "#10b981"),
        ("Total Active User Sessions", f"{total_usage_all:,}", "#3b82f6"),
        ("Resources Tracked", f"{len(data)}", "#8b5cf6"),
        ("Busiest Training Year", f"{busiest_t_year[0]} ({busiest_t_year[1]:,})", "#f59e0b"),
    ]
    for label, val, accent in kpis:
        html.append(f"""
        <div style='background-color: white; border: 1px solid #e2e8f0; border-left: 4px solid {accent}; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);'>
          <div style='font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;'>{label}</div>
          <div style='font-size: 19px; color: #0f172a; font-weight: 700; margin-top: 4px;'>{val}</div>
        </div>
        """)
    html.append("</div>")

    # Filter / Sort / Metric / View Controls Toolbar
    html.append("""
    <div style='background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 18px; margin-bottom: 20px; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);'>
      <div style='display: flex; align-items: center; gap: 12px; flex-wrap: wrap; flex: 1;'>
        <input type='text' id='trainingSearchInput' placeholder='🔍 Search resources...' 
               oninput='let q=this.value.toLowerCase(); document.querySelectorAll(".training-res-card").forEach(c => { c.style.display = c.getAttribute("data-name").toLowerCase().includes(q) ? "" : "none"; });' 
               style='padding: 7px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13.5px; width: 250px; outline: none;'>
        
        <select onchange='let v=this.value; let container=document.getElementById("trainingCardsGrid"); let cards=Array.from(container.querySelectorAll(".training-res-card")); cards.sort((a,b) => { if(v==="name") return a.getAttribute("data-name").localeCompare(b.getAttribute("data-name")); if(v==="training-desc") return parseInt(b.getAttribute("data-training")) - parseInt(a.getAttribute("data-training")); if(v==="usage-desc") return parseInt(b.getAttribute("data-usage")) - parseInt(a.getAttribute("data-usage")); if(v==="recent-desc") return parseInt(b.getAttribute("data-recent")) - parseInt(a.getAttribute("data-recent")); return 0; }); cards.forEach(c => container.appendChild(c));' 
                style='padding: 7px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13.5px; background-color: white; color: #334155; cursor: pointer;'>
          <option value='name'>Sort by Name (A-Z)</option>
          <option value='training-desc'>Sort by Trainings (Highest First)</option>
          <option value='usage-desc'>Sort by Unique Users (Highest First)</option>
          <option value='recent-desc'>Sort by Recent Activity (Highest First)</option>
        </select>

        <div class='btn-group' role='group' style='display: inline-flex;'>
          <button type='button' class='btn btn-sm btn-primary active' id='btnShowBoth' onclick='document.querySelectorAll(".series-usage").forEach(el=>el.style.display=""); document.querySelectorAll(".series-training").forEach(el=>el.style.display=""); document.querySelectorAll(".col-usage").forEach(el=>el.style.display=""); document.querySelectorAll(".col-training").forEach(el=>el.style.display=""); document.getElementById("btnShowBoth").classList.add("btn-primary"); document.getElementById("btnShowBoth").classList.remove("btn-outline-primary"); document.getElementById("btnShowUsage").classList.remove("btn-primary"); document.getElementById("btnShowUsage").classList.add("btn-outline-primary"); document.getElementById("btnShowTraining").classList.remove("btn-primary"); document.getElementById("btnShowTraining").classList.add("btn-outline-primary");' style='font-size: 12.5px; padding: 6px 11px;'>Both</button>
          <button type='button' class='btn btn-sm btn-outline-primary' id='btnShowTraining' onclick='document.querySelectorAll(".series-usage").forEach(el=>el.style.display="none"); document.querySelectorAll(".series-training").forEach(el=>el.style.display=""); document.querySelectorAll(".col-usage").forEach(el=>el.style.display="none"); document.querySelectorAll(".col-training").forEach(el=>el.style.display=""); document.getElementById("btnShowTraining").classList.add("btn-primary"); document.getElementById("btnShowTraining").classList.remove("btn-outline-primary"); document.getElementById("btnShowBoth").classList.remove("btn-primary"); document.getElementById("btnShowBoth").classList.add("btn-outline-primary"); document.getElementById("btnShowUsage").classList.remove("btn-primary"); document.getElementById("btnShowUsage").classList.add("btn-outline-primary");' style='font-size: 12.5px; padding: 6px 11px;'>🟩 Training Only</button>
          <button type='button' class='btn btn-sm btn-outline-primary' id='btnShowUsage' onclick='document.querySelectorAll(".series-usage").forEach(el=>el.style.display=""); document.querySelectorAll(".series-training").forEach(el=>el.style.display="none"); document.querySelectorAll(".col-usage").forEach(el=>el.style.display=""); document.querySelectorAll(".col-training").forEach(el=>el.style.display="none"); document.getElementById("btnShowUsage").classList.add("btn-primary"); document.getElementById("btnShowUsage").classList.remove("btn-outline-primary"); document.getElementById("btnShowBoth").classList.remove("btn-primary"); document.getElementById("btnShowBoth").classList.add("btn-outline-primary"); document.getElementById("btnShowTraining").classList.remove("btn-primary"); document.getElementById("btnShowTraining").classList.add("btn-outline-primary");' style='font-size: 12.5px; padding: 6px 11px;'>🟦 Users Only</button>
        </div>
      </div>
      
      <div>
        <button type='button' onclick='let g=document.getElementById("trainingCardsGrid"); let t=document.getElementById("trainingTableContainer"); if(t.style.display==="none"){ t.style.display="block"; g.style.display="none"; this.innerHTML="📊 Show Graphs"; } else { t.style.display="none"; g.style.display="grid"; this.innerHTML="📋 Show Data Table"; }' 
                class='btn btn-outline-secondary btn-sm' style='font-weight: 500; font-size: 13px; padding: 6px 12px;'>📋 Show Data Table</button>
      </div>
    </div>
    """)

    # Cards Grid
    html.append("<div id='trainingCardsGrid' style='display: grid; grid-template-columns: repeat(auto-fill, minmax(460px, 1fr)); gap: 20px;'>")

    sorted_resources = sorted(data.items(), key=lambda x: x[1]['name'].lower())

    for res_id, info in sorted_resources:
        name = info['name']
        usage_counts = info['usage']
        training_counts = info['training']

        total_u = sum(usage_counts.values())
        total_t = sum(training_counts.values())
        recent_u = usage_counts.get(all_years[-1], 0)
        recent_t = training_counts.get(all_years[-1], 0)

        # YoY Trend for training compared to prior year
        prev_t = training_counts.get(all_years[-2], 0) if len(all_years) >= 2 else 0
        diff_t = recent_t - prev_t
        if prev_t > 0:
            pct_t = (diff_t / float(prev_t)) * 100
            if diff_t > 0:
                trend_t_badge = f"<span style='background-color: #dcfce7; color: #166534; font-weight: 600; padding: 3px 8px; border-radius: 12px; font-size: 11px;'>Trained: ▲ +{diff_t} (+{pct_t:.0f}%)</span>"
            elif diff_t < 0:
                trend_t_badge = f"<span style='background-color: #fee2e2; color: #991b1b; font-weight: 600; padding: 3px 8px; border-radius: 12px; font-size: 11px;'>Trained: ▼ {diff_t} ({pct_t:.0f}%)</span>"
            else:
                trend_t_badge = f"<span style='background-color: #f1f5f9; color: #475569; font-weight: 600; padding: 3px 8px; border-radius: 12px; font-size: 11px;'>Trained: ▶ 0%</span>"
        elif recent_t > 0:
            trend_t_badge = f"<span style='background-color: #dcfce7; color: #166534; font-weight: 600; padding: 3px 8px; border-radius: 12px; font-size: 11px;'>Trained: ▲ +{recent_t}</span>"
        else:
            trend_t_badge = f"<span style='background-color: #f1f5f9; color: #94a3b8; font-weight: 500; padding: 3px 8px; border-radius: 12px; font-size: 11px;'>Trained: 0</span>"

        peak_u = 0
        peak_u_yr = "-"
        for yr in all_years:
            c = usage_counts.get(yr, 0)
            if c > peak_u:
                peak_u = c
                peak_u_yr = yr

        peak_t = 0
        peak_t_yr = "-"
        for yr in all_years:
            c = training_counts.get(yr, 0)
            if c > peak_t:
                peak_t = c
                peak_t_yr = yr

        chart_svg = generate_combined_bar_chart(res_id, name, all_years, usage_counts, training_counts, current_year_str)

        html.append(f"""
        <div class='training-res-card' data-name='{escape(name)}' data-usage='{total_u}' data-training='{total_t}' data-recent='{recent_u + recent_t}' 
             style='background-color: white; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); display: flex; flex-direction: column; justify-content: space-between;'>
          
          <div>
            <div style='display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 8px;'>
              <div>
                <h4 style='margin: 0; font-size: 16px; font-weight: 700; color: #0f172a;'>{escape(name)}</h4>
                <span style='font-size: 11px; color: #94a3b8;'>Resource #{res_id}</span>
              </div>
              <div style='display: flex; align-items: center; gap: 6px; flex-wrap: wrap; justify-content: flex-end;'>
                {trend_t_badge}
                <span style='background-color: #059669; color: white; font-weight: 700; padding: 3px 8px; border-radius: 12px; font-size: 11px;'>{total_t:,} trained</span>
                <span style='background-color: #2563eb; color: white; font-weight: 700; padding: 3px 8px; border-radius: 12px; font-size: 11px;'>{total_u:,} users</span>
              </div>
            </div>

            <!-- Chart Legend -->
            <div style='display: flex; align-items: center; gap: 16px; font-size: 11.5px; margin-bottom: 6px; color: #475569;'>
              <span class='series-usage' style='display: inline-flex; align-items: center; gap: 5px;'>
                <span style='width: 10px; height: 10px; border-radius: 2px; background: linear-gradient(to bottom, #3b82f6, #1d4ed8); display: inline-block;'></span> Unique Active Users
              </span>
              <span class='series-training' style='display: inline-flex; align-items: center; gap: 5px;'>
                <span style='width: 10px; height: 10px; border-radius: 2px; background: linear-gradient(to bottom, #10b981, #047857); display: inline-block;'></span> Members Trained
              </span>
            </div>
            
            <div style='margin-top: 4px;'>
              {chart_svg}
            </div>
          </div>
          
          <div style='display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #f1f5f9; padding-top: 10px; margin-top: 8px; font-size: 11px; color: #64748b;'>
            <span><strong>Peak Trained:</strong> {peak_t} ({peak_t_yr})</span>
            <span><strong>Peak Users:</strong> {peak_u} ({peak_u_yr})</span>
            <span><strong>Latest ({all_years[-1]}):</strong> {recent_t} trained, {recent_u} users</span>
          </div>
        </div>
        """)

    html.append("</div>")  # End cards grid

    # Cross-tab Summary Table
    html.append("<div id='trainingTableContainer' style='display: none; background-color: white; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); overflow-x: auto;'>")
    html.append("<h4 style='margin: 0 0 14px 0; font-size: 16px; color: #0f172a; font-weight: 700;'>Year-by-Year Resource Training & Utilization Summary Table</h4>")
    html.append("<table class='table table-bordered table-striped table-hover table-sm' style='font-size: 12.5px; margin: 0;'>")
    html.append("<thead class='thead-dark'><tr>")
    html.append("<th rowspan='2' style='vertical-align: middle; padding: 6px 10px;'>Resource Name</th>")
    html.append("<th rowspan='2' style='vertical-align: middle; padding: 6px 8px; text-align: center;'>ID</th>")
    for yr in all_years:
        col_title = yr if yr != current_year_str else f"{yr}*"
        html.append(f"<th colspan='2' style='text-align: center; border-left: 2px solid #475569;'>{col_title}</th>")
    html.append("<th colspan='2' style='text-align: center; background-color: #1e293b; color: white; border-left: 2px solid #0f172a;'>Total</th>")
    html.append("</tr><tr>")
    for yr in all_years:
        html.append("<th class='col-training' style='font-size: 11px; text-align: right; background-color: #064e3b; color: white; border-left: 2px solid #475569;'>Trained</th>")
        html.append("<th class='col-usage' style='font-size: 11px; text-align: right; background-color: #1e3a8a; color: white;'>Users</th>")
    html.append("<th class='col-training' style='font-size: 11px; text-align: right; background-color: #064e3b; color: white; border-left: 2px solid #0f172a;'>Trained</th>")
    html.append("<th class='col-usage' style='font-size: 11px; text-align: right; background-color: #1e3a8a; color: white;'>Users</th>")
    html.append("</tr></thead><tbody>")

    for res_id, info in sorted_resources:
        name = info['name']
        usage_counts = info['usage']
        training_counts = info['training']
        res_u_total = sum(usage_counts.values())
        res_t_total = sum(training_counts.values())

        html.append("<tr>")
        html.append(f"<td style='font-weight: 600;'>{escape(name)}</td>")
        html.append(f"<td style='text-align: center; color: #64748b;'>{res_id}</td>")
        for yr in all_years:
            u_c = usage_counts.get(yr, 0)
            t_c = training_counts.get(yr, 0)
            u_str = f"{u_c:,}" if u_c > 0 else "<span style='color: #cbd5e1;'>0</span>"
            t_str = f"{t_c:,}" if t_c > 0 else "<span style='color: #cbd5e1;'>0</span>"
            html.append(f"<td class='col-training' style='text-align: right; color: #047857; border-left: 1px solid #e2e8f0;'>{t_str}</td>")
            html.append(f"<td class='col-usage' style='text-align: right;'>{u_str}</td>")
        html.append(f"<td class='col-training' style='text-align: right; font-weight: 700; background-color: #ecfdf5; color: #047857; border-left: 2px solid #94a3b8;'>{res_t_total:,}</td>")
        html.append(f"<td class='col-usage' style='text-align: right; font-weight: 700; background-color: #eff6ff;'>{res_u_total:,}</td>")
        html.append("</tr>")

    # Table Totals Row
    html.append("<tr style='font-weight: 700; background-color: #e2e8f0; border-top: 2px solid #0f172a;'>")
    html.append("<td colspan='2' style='padding: 8px 10px;'>TOTAL</td>")
    for yr in all_years:
        html.append(f"<td class='col-training' style='padding: 8px 10px; text-align: right; color: #047857; border-left: 1px solid #cbd5e1;'>{year_training_totals[yr]:,}</td>")
        html.append(f"<td class='col-usage' style='padding: 8px 10px; text-align: right;'>{year_usage_totals[yr]:,}</td>")
    html.append(f"<td class='col-training' style='padding: 8px 10px; text-align: right; background-color: #d1fae5; color: #047857; border-left: 2px solid #0f172a;'>{total_training_all:,}</td>")
    html.append(f"<td class='col-usage' style='padding: 8px 10px; text-align: right; background-color: #dbeafe;'>{total_usage_all:,}</td>")
    html.append("</tr>")

    html.append("</tbody></table>")
    html.append("</div>")  # End table container

    html.append("</div>")  # End outer div
    html.append("\n<pre>")
    return "".join(html)


def main():
    # Allow testing with demo data if requested or in environment
    if os.environ.get('TRAINING_REPORT_DEMO') or os.environ.get('USAGE_REPORT_DEMO'):
        demo_data = {
            1: {
                'name': 'Epilog Laser',
                'usage': {'2018': 85, '2019': 140, '2020': 110, '2021': 195, '2022': 230, '2023': 280, '2024': 260, '2025': 275, '2026': 210},
                'training': {'2018': 35, '2019': 58, '2020': 42, '2021': 75, '2022': 90, '2023': 112, '2024': 98, '2025': 105, '2026': 82}
            },
            2: {
                'name': 'Bridgeport Mill',
                'usage': {'2018': 25, '2019': 38, '2020': 30, '2021': 48, '2022': 55, '2023': 60, '2024': 68, '2025': 75, '2026': 52},
                'training': {'2018': 12, '2019': 20, '2020': 15, '2021': 25, '2022': 30, '2023': 28, '2024': 35, '2025': 40, '2026': 29}
            },
            3: {
                'name': '3D Printers',
                'usage': {'2019': 95, '2020': 120, '2021': 185, '2022': 240, '2023': 310, '2024': 295, '2025': 320, '2026': 245},
                'training': {'2019': 45, '2020': 50, '2021': 85, '2022': 110, '2023': 130, '2024': 125, '2025': 140, '2026': 95}
            },
            4: {
                'name': 'Wood Lathe',
                'usage': {'2018': 32, '2019': 40, '2020': 28, '2021': 55, '2022': 62, '2023': 75, '2024': 70, '2025': 82, '2026': 60},
                'training': {'2018': 18, '2019': 22, '2020': 14, '2021': 30, '2022': 35, '2023': 44, '2024': 41, '2025': 48, '2026': 36}
            },
            5: {
                'name': 'TIG Welder',
                'usage': {'2018': 18, '2019': 28, '2020': 22, '2021': 36, '2022': 44, '2023': 52, '2024': 48, '2025': 58, '2026': 42},
                'training': {'2018': 8, '2019': 15, '2020': 11, '2021': 19, '2022': 24, '2023': 29, '2024': 26, '2025': 31, '2026': 20}
            },
            6: {
                'name': 'CNC Router',
                'usage': {'2020': 35, '2021': 72, '2022': 105, '2023': 135, '2024': 128, '2025': 145, '2026': 112},
                'training': {'2020': 16, '2021': 38, '2022': 52, '2023': 65, '2024': 60, '2025': 72, '2026': 55}
            },
        }
        print(render_report_html(demo_data, "Resource Training & Usage Trends"))
        sys.exit(0)

    try:
        conn = sqlite3.connect(LOG_DB)
        conn.execute(f'ATTACH DATABASE "{MAKEIT_DB}" AS makeit')
        cursor = conn.cursor()

        since_date = os.environ.get('REPORT_SINCE', '')

        # 1. Query Trainings Granted
        train_query = """
            SELECT 
                r.id AS resource_id,
                r.name AS resource_name,
                strftime('%Y', l.time_logged) AS year,
                COUNT(*) AS training_count
            FROM main.log AS l
            JOIN makeit.resources AS r ON l.resource_id = r.id
            WHERE l.event_type = ?
              AND l.time_logged IS NOT NULL
        """
        params_t = [EVENT_ACCESS_GRANTED]
        if since_date:
            train_query += " AND l.time_logged >= ?"
            params_t.append(since_date)
        train_query += " GROUP BY r.id, r.name, strftime('%Y', l.time_logged) ORDER BY r.name, year;"
        cursor.execute(train_query, params_t)
        train_rows = cursor.fetchall()

        # 2. Query Unique Active Users
        usage_query = """
            SELECT 
                r.id AS resource_id,
                r.name AS resource_name,
                strftime('%Y', l.time_logged) AS year,
                COUNT(DISTINCT l.member_id) AS unique_members
            FROM main.log AS l
            JOIN makeit.resources AS r ON l.resource_id = r.id
            WHERE (l.event_type = ? OR l.event_type = ?)
              AND l.member_id > 0
              AND l.time_logged IS NOT NULL
        """
        params_u = [EVENT_TOOL_LOGIN, EVENT_ENTRY_ALLOWED]
        if since_date:
            usage_query += " AND l.time_logged >= ?"
            params_u.append(since_date)
        usage_query += " GROUP BY r.id, r.name, strftime('%Y', l.time_logged) ORDER BY r.name, year;"
        cursor.execute(usage_query, params_u)
        usage_rows = cursor.fetchall()

        conn.close()

    except Exception as e:
        print("HTML:\n</pre>")
        print(f"<div style='padding: 20px; font-family: sans-serif; background-color: white; border-radius: 8px; border: 1px solid #fee2e2;'>")
        print(f"<h3 style='color: #dc2626; margin-top: 0;'>Database Notice</h3>")
        print(f"<p style='color: #4b5563;'>Could not query training logs: {escape(str(e))}</p>")
        print("</div>\n<pre>")
        sys.exit(0)

    if not usage_rows and not train_rows:
        print("HTML:\n</pre>")
        print("<div style='padding: 20px; font-family: sans-serif; background-color: white; border-radius: 8px;'>")
        print("<h3 style='color: #334155; margin-top: 0;'>Resource Training Trends</h3>")
        print("<p style='color: #64748b;'>No training or usage records found in log database.</p>")
        print("</div>\n<pre>")
        sys.exit(0)

    # Structure data: {resource_id: {'name': str, 'usage': {year: count}, 'training': {year: count}}}
    data = {}
    for res_id, res_name, yr, count in usage_rows:
        if not yr:
            continue
        if res_id not in data:
            data[res_id] = {
                'name': res_name if res_name else f"Resource #{res_id}",
                'usage': {},
                'training': {}
            }
        data[res_id]['usage'][yr] = count

    for res_id, res_name, yr, count in train_rows:
        if not yr:
            continue
        if res_id not in data:
            data[res_id] = {
                'name': res_name if res_name else f"Resource #{res_id}",
                'usage': {},
                'training': {}
            }
        data[res_id]['training'][yr] = count

    print(render_report_html(data, "Resource Training & Usage Trends"))
    sys.exit(0)


if __name__ == '__main__':
    main()
