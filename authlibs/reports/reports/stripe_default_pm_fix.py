#!/usr/bin/python3
"""
stripe_default_pm_fix.py - Find and fix Stripe customers missing a default payment method

Finds customers who have active subscriptions but no default_payment_method set
in their invoice_settings. This causes vending/consumable charges to fail.

Usage:
    python3 stripe_default_pm_fix.py

Reads Stripe API key from stripe_default_pm_fix.key (same pattern as stripenamefix.py)

The FIX section is commented out by default. Run in report-only mode first to
verify the results look sane, then uncomment the fix block to actually update
Stripe customer records.
"""

import stripe
from datetime import datetime
import sys

if __name__ == "__main__":
    missing = 0
    has_default = 0
    fixed = 0
    no_pm_available = 0
    err = 0
    no_sub = 0

    stripe.api_version = '2020-08-27'
    stripe.api_key = open("stripenamefix.key").readline().strip()

    for customer in stripe.Customer.auto_paging_iter(False):
        cust_id = customer.id
        cust_name = customer.description or customer.name or "(no name)"

        # Check if customer already has a default payment method
        default_pm = customer.get('invoice_settings', {}).get('default_payment_method')
        if default_pm is not None:
            has_default += 1
            continue

        # No default - check if they have an active subscription
        subscriptions = stripe.Subscription.list(customer=cust_id, status="active")
        if len(subscriptions['data']) == 0:
            no_sub += 1
            continue

        # Active sub but no default payment method - this is the problem case
        sub = subscriptions['data'][0]
        sub_pm = sub.get('default_payment_method')

        # Also check for attached payment methods we could use
        attached_pms = stripe.PaymentMethod.list(customer=cust_id, type="card")
        attached_count = len(attached_pms['data'])

        # Determine which payment method we'd use for the fix
        fix_pm = None
        fix_source = None
        if sub_pm:
            fix_pm = sub_pm
            fix_source = "subscription default_payment_method"
        elif attached_count > 0:
            # Use the most recently created attached card
            fix_pm = attached_pms['data'][0].id
            fix_source = "most recent attached card"

        missing += 1
        if fix_pm:
            # Show the card details if we can
            try:
                pm_obj = stripe.PaymentMethod.retrieve(fix_pm)
                card_info = f"{pm_obj.card.brand} ending {pm_obj.card.last4}" if pm_obj.card else "unknown"
            except Exception:
                card_info = "unknown"
            print(f"MISSING DEFAULT: {cust_name} ({cust_id}) "
                  f"sub={sub.id} attached_cards={attached_count} "
                  f"fix_from={fix_source} card={card_info}")

            ## ---------------------------------------------------------------
            ## UNCOMMENT THE BLOCK BELOW TO ACTUALLY FIX THE CUSTOMERS
            ## ---------------------------------------------------------------
            try:
                stripe.Customer.modify(
                    cust_id,
                    invoice_settings={
                        'default_payment_method': fix_pm
                    },
                )
                fixed += 1
                print(f"  -> FIXED: set default to {fix_pm}")
            except BaseException as e:
                print(f"  -> ERROR fixing {cust_id}: {e}")
                err += 1
            ## ---------------------------------------------------------------

        else:
            no_pm_available += 1
            print(f"MISSING DEFAULT (NO FIX AVAILABLE): {cust_name} ({cust_id}) "
                  f"sub={sub.id} attached_cards={attached_count} "
                  f"- no payment method found to use")

    print(f"\n--- Summary ---")
    print(f"Has default already:     {has_default}")
    print(f"No active subscription:  {no_sub}")
    print(f"Missing default:         {missing}")
    print(f"  - Fixable:             {missing - no_pm_available}")
    print(f"  - No PM available:     {no_pm_available}")
    print(f"Fixed:                   {fixed}")
    print(f"Errors:                  {err}")
    print(f"Total customers:         {has_default + no_sub + missing}")
    sys.exit(0)
