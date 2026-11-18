#!/usr/bin/env python3
"""
Member Count V2 Report

Accurately counts members by:
1. Loading repgroups.dat to map Stripe product/plan IDs to membership categories.
   ONLY these repgroups values are recognized as memberships:
   - FreeMember        -> free seats
   - FirstMembership   -> free seats (FIRST robotics teams)
   - GroupMember        -> paid seats
   - HobbyistMembership -> paid seats
   - ProMembership      -> paid seats
   - ProDuoMember       -> paid seats
   Any other repgroups value (e.g. Workspace) is ignored.
2. Classifying subscriptions into Paid vs Free:
   - FreeMember / FirstMembership product codes = Free
   - 100% off / Exempt coupons = Overridden to Free
   - All other recognized memberships = Paid
3. Parsing Stripe metadata (e.g., 'names', 'emails') for individual seat counts.
   - Defaults ProDuoMember to 2 seats if no metadata list is present.
4. Displaying a detailed breakdown by Group and Coupon type.
"""

import os
import re
import sys
import json
import stripe
from datetime import datetime

# Only these repgroups values are recognized as memberships
VALID_GROUPS = {
    'FreeMember',
    'FirstMembership',
    'GroupMember',
    'HobbyistMembership',
    'ProMembership',
    'ProDuoMember'
}

# These groups are always counted as free seats
FREE_GROUPS = {'FreeMember', 'FirstMembership'}

EXEMPT_COUPONS = {
    '100PERCENTOFF',
    'NonProfit -Free 1yr Memberships',
    '100% off in perpetuity- Do NOT use',
    'LCpqqG55'
}

# Normalize repgroups values that are synonyms for canonical group names
REPGROUP_SYNONYMS = {
    'ProMember': 'ProMembership',
    'GroupPro': 'ProMembership',
    'Group_Pro': 'ProMembership',
}

def load_repgroups():
    """Load repgroups.dat and return a dict mapping product/plan IDs to group names."""
    group_map = {}
    paths = [
        'repgroups.dat',
        '../repgroups.dat',
        '../../repgroups.dat',
        '/var/www/authbackend/repgroups.dat'
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            parts = line.split()
                            if len(parts) >= 2:
                                raw_group = parts[1]
                                # Normalize synonyms
                                group_map[parts[0]] = REPGROUP_SYNONYMS.get(raw_group, raw_group)
                print(f"Loaded repgroups from {p}: {len(group_map)} entries", file=sys.stderr)
                break
            except Exception as e:
                print(f"Warning: Error reading {p}: {e}", file=sys.stderr)

    # Always add standard Stripe plan ID fallbacks (these use plan ID, not product ID)
    group_map.setdefault('hobbyist', 'HobbyistMembership')
    group_map.setdefault('pro', 'ProMembership')
    group_map.setdefault('produo', 'ProDuoMember')
    group_map.setdefault('group_pro', 'ProMembership')
    group_map.setdefault('group', 'GroupMember')
    group_map.setdefault('group_hobbyist', 'HobbyistMembership')

    return group_map

def get_coupon_info(s):
    """Extract coupon info from a Stripe subscription. Returns (is_100pct_free, coupon_label)."""
    try:
        discount = s.get('discount')
        if discount and discount.get('coupon'):
            c = discount['coupon']
            c_name = c.get('name') or ''
            c_id = c.get('id') or ''
            pct = c.get('percent_off')
            is_100_pct = (pct == 100) or (c_name in EXEMPT_COUPONS) or (c_id in EXEMPT_COUPONS)
            coupon_label = c_name if c_name else c_id
            return is_100_pct, coupon_label
    except Exception:
        pass
    return False, "No Coupon"

def count_seats(s, group_name, plan_id=''):
    """Count individual seats from Stripe metadata, quantities, or plan defaults."""
    candidates = []

    # 1. Gather plan_id and product_id
    plan = s.get('plan') or {}
    if not plan_id:
        plan_id = plan.get('id', '')
    product_id = plan.get('product', '')

    items = s.get('items', {}).get('data', []) if isinstance(s.get('items'), dict) else []
    if not product_id and items:
        item_plan = items[0].get('plan') or items[0].get('price') or {}
        if not plan_id:
            plan_id = item_plan.get('id', '')
        product_id = item_plan.get('product', '')

    # 2. Gather metadata from customer, items, and root subscription
    meta = {}
    cust = s.get('customer')
    if isinstance(cust, dict):
        meta.update(cust.get('metadata') or {})
    for item in items:
        if isinstance(item, dict) and item.get('metadata'):
            meta.update(item['metadata'])
    if s.get('metadata') and isinstance(s.get('metadata'), dict):
        meta.update(s['metadata'])

    # 3. Normalize metadata keys
    norm_meta = {}
    for k, v in meta.items():
        if k is not None and v is not None:
            norm_key = re.sub(r'[\s\-_]+', '_', str(k).strip().lower())
            norm_meta[norm_key] = str(v).strip()

    # 4. Check list-style metadata fields
    list_keys = [
        'names', 'emails', 'members', 'users', 'students', 'members_list',
        'team_members', 'group_members', 'member_names', 'member_emails',
        'additional_members', 'roster', 'people', 'subscribers', 'seats_list',
        'attendees', 'family_members', 'additional_names'
    ]
    for key in list_keys:
        val = norm_meta.get(key)
        if val:
            if val.startswith('[') and val.endswith(']'):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list) and len(parsed) > 1:
                        candidates.append(len(parsed))
                        continue
                except Exception:
                    pass
            split_items = [item.strip() for item in re.split(r'[,;\n\r|/]+', val) if item.strip()]
            if len(split_items) > 1:
                candidates.append(len(split_items))

    # 5. Check numbered member keys (e.g. member_1..member_4, name1..name4, email_1..email_4)
    numbered_indices = set()
    for norm_k, val in norm_meta.items():
        if val:
            m = re.match(r'^(?:member|name|user|student|email|seat|attendee)_?([0-9]+)$', norm_k)
            if m:
                numbered_indices.add(m.group(1))
    if len(numbered_indices) > 1:
        candidates.append(len(numbered_indices))

    # 6. Check numeric metadata fields
    num_keys = [
        'count', 'seats', 'num_members', 'total_members', 'quantity',
        'num_seats', 'seat_count', 'member_count', 'group_size', 'team_size',
        'qty', 'number_of_members', 'number_of_seats', 'members_count', 'total_seats'
    ]
    for key in num_keys:
        val = norm_meta.get(key)
        if val:
            try:
                num = int(val)
                if num > 1:
                    candidates.append(num)
            except ValueError:
                pass

    # 7. Check Stripe native quantity on subscription and items
    sub_qty = s.get('quantity')
    if isinstance(sub_qty, int) and sub_qty > 1:
        candidates.append(sub_qty)

    for item in items:
        if isinstance(item, dict):
            item_qty = item.get('quantity')
            if isinstance(item_qty, int) and item_qty > 1:
                candidates.append(item_qty)

    # 8. Check plan-based defaults
    plan_str = f"{plan_id} {product_id} {s.get('description', '')}".lower()
    for v in norm_meta.values():
        if 'group_pro' in v.lower():
            plan_str += ' group_pro'

    if 'group_pro' in plan_str:
        candidates.append(4)
    elif group_name == 'ProDuoMember' or 'produo' in plan_str:
        candidates.append(2)

    if candidates:
        return max(candidates)
    return 1

def main():
    try:
        stripe.api_key = open("stripenamefix.key").readline().strip()
    except FileNotFoundError:
        key_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../stripenamefix.key"))
        if os.path.exists(key_path):
            stripe.api_key = open(key_path).readline().strip()
        else:
            print("Error: stripenamefix.key not found.", file=sys.stderr)
            sys.exit(1)

    stripe.api_version = '2020-08-27'
    repgroups = load_repgroups()

    # Structure: counts[group_name][coupon_name] = {'paid': 0, 'free': 0, 'total': 0, 'subs': 0}
    counts = {}
    processed_subs = set()
    total_processed = 0

    for s in stripe.Subscription.auto_paging_iter():
        if s['id'] in processed_subs:
            continue
        processed_subs.add(s['id'])

        # Active check: use Stripe's status field directly
        # canceled_at being set only means "cancel at period end" - sub is still active
        sub_status = s.get('status', '')
        if sub_status not in ('active', 'trialing'):
            continue

        # Extract plan/product info - try top-level plan first, then subscription items
        plan = s.get('plan') or {}
        plan_id = plan.get('id', '')
        product_id = plan.get('product', '')

        # Fallback: check subscription items if top-level plan is missing product
        if not product_id:
            items = s.get('items', {}).get('data', [])
            if items:
                item_plan = items[0].get('plan') or items[0].get('price') or {}
                if not plan_id:
                    plan_id = item_plan.get('id', '')
                product_id = item_plan.get('product', '')

        # Look up group from repgroups by product_id first, then plan_id
        group_name = repgroups.get(product_id) or repgroups.get(plan_id)

        # Fallback: plan_id substring matching if not explicitly in repgroups
        if not group_name:
            plan_lower = (plan_id or '').lower()
            if 'group_pro' in plan_lower:
                group_name = 'ProMembership'
            elif 'produo' in plan_lower:
                group_name = 'ProDuoMember'
            elif 'group' in plan_lower:
                group_name = 'GroupMember'
            elif 'pro' in plan_lower:
                group_name = 'ProMembership'
            elif 'hobbyist' in plan_lower:
                group_name = 'HobbyistMembership'

        # Strict whitelist: only process recognized membership groups
        if not group_name or group_name not in VALID_GROUPS:
            continue

        total_processed += 1
        seats = count_seats(s, group_name, plan_id)
        is_free_coupon, coupon_name = get_coupon_info(s)

        # Free if the group is inherently free OR has a 100% exempt coupon
        is_free = (group_name in FREE_GROUPS) or is_free_coupon

        if group_name not in counts:
            counts[group_name] = {}

        if coupon_name not in counts[group_name]:
            counts[group_name][coupon_name] = {'paid': 0, 'free': 0, 'total': 0, 'subs': 0}

        entry = counts[group_name][coupon_name]
        entry['subs'] += 1
        entry['total'] += seats

        if is_free:
            entry['free'] += seats
        else:
            entry['paid'] += seats

    # Print HTML output
    print("HTML:\n</pre>")
    print("<div style='font-family: Arial, sans-serif; padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>")
    print("<h2 style='color: #333; margin-top: 0;'>Member Count V2 Report (Product & Metadata Aware)</h2>")
    print(f"<p class='text-muted'>Processed {total_processed} active membership subscriptions.</p>")

    grand_paid = 0
    grand_free = 0
    grand_all = 0
    grand_subs = 0

    print("<table class='table table-bordered mt-3'>")
    print("<thead class='thead-dark'><tr><th>Group / Coupon</th><th class='text-right'>Total Seats</th><th class='text-right'>Paid Seats</th><th class='text-right'>Free Seats</th><th class='text-right'>Subscriptions</th></tr></thead>")
    print("<tbody>")

    for g in sorted(counts.keys()):
        g_data = counts[g]
        g_paid = sum(c['paid'] for c in g_data.values())
        g_free = sum(c['free'] for c in g_data.values())
        g_tot = sum(c['total'] for c in g_data.values())
        g_subs = sum(c['subs'] for c in g_data.values())

        grand_paid += g_paid
        grand_free += g_free
        grand_all += g_tot
        grand_subs += g_subs

        # Group header row
        print(f"<tr class='table-secondary'><td colspan='5'><strong>{g}</strong> (Total Seats: {g_tot} | Paid: {g_paid} | Free: {g_free} | Subscriptions: {g_subs})</td></tr>")

        for coupon in sorted(g_data.keys()):
            c_info = g_data[coupon]
            print(f"<tr><td style='padding-left: 25px;'>{coupon}</td><td class='text-right'>{c_info['total']}</td><td class='text-right'>{c_info['paid']}</td><td class='text-right'>{c_info['free']}</td><td class='text-right'>{c_info['subs']}</td></tr>")

    print("<tr class='table-info' style='font-size: 1.1em;'>")
    print(f"<td><strong>Grand Total</strong></td><td class='text-right'><strong>{grand_all}</strong></td><td class='text-right'><strong>{grand_paid}</strong></td><td class='text-right'><strong>{grand_free}</strong></td><td class='text-right'><strong>{grand_subs}</strong></td>")
    print("</tr>")
    print("</tbody></table>")

    print("</div>\n<pre>")

    sys.exit(0)

if __name__ == '__main__':
    main()
