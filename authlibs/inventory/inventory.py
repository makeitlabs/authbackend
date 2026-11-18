# vim:shiftwidth=2:expandtab

from ..templateCommon import  *
from datetime import datetime
import stripe
from authlibs.slackutils import send_slack_message

blueprint = Blueprint("inventory", __name__, template_folder='templates', static_folder="static", url_prefix="/store")


def get_current_quantity(purchasable_id):
    """Get the current inventory count for a purchasable item.
    Returns None if no inventory records exist (untracked)."""
    latest = InventoryLog.query.filter(
        InventoryLog.purchasable_id == purchasable_id
    ).order_by(InventoryLog.id.desc()).first()
    if latest is None:
        return None
    return latest.new_quantity


def is_inventory_tracked(purchasable_id):
    """Returns True if this purchasable has any inventory records."""
    return InventoryLog.query.filter(
        InventoryLog.purchasable_id == purchasable_id
    ).count() > 0


def get_group_items(resource_id):
    """Get all purchasables for a resource, split into tracked and untracked."""
    all_purchasables = Purchasable.query.filter(Purchasable.resource_id == resource_id).all()
    tracked = []
    untracked = []
    for p in all_purchasables:
        qty = get_current_quantity(p.id)
        item = {
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'price': p.price,
            'pricestr': "" if p.price is None else f"${p.price/100.0:0.2f}",
            'priceval': 0 if p.price is None else p.price,
            'current_qty': qty,
        }
        if qty is not None:
            tracked.append(item)
        else:
            untracked.append(item)
    return tracked, untracked


@blueprint.route('/group/<int:purchasable_id>', methods=['GET'])
@login_required
def store(purchasable_id):
    """Store page for a resource group, entered via any purchasable in the group."""
    p = Purchasable.query.filter(Purchasable.id == purchasable_id).one_or_none()
    if not p:
        flash("Item not found", "danger")
        return redirect(url_for('purchasables.purchasables'))
    if p.resource_id is None:
        flash("This item is not assigned to a resource group", "danger")
        return redirect(url_for('purchasables.purchasables'))

    res = Resource.query.filter(Resource.id == p.resource_id).one_or_none()
    if not res:
        flash("Resource not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    tracked, untracked = get_group_items(res.id)
    is_arm = current_user.is_specific_arm(resource_id=res.id) or current_user.privs('Admin')

    return render_template('store.html',
        resource=res,
        tracked=sorted(tracked, key=lambda x: x['name']),
        untracked=sorted(untracked, key=lambda x: x['name']),
        is_arm=is_arm,
        purchasable_id=purchasable_id)


@blueprint.route('/group/<int:purchasable_id>/purchase', methods=['POST'])
@login_required
def store_purchase(purchasable_id):
    """Multi-item cart purchase with single Stripe invoice."""
    p = Purchasable.query.filter(Purchasable.id == purchasable_id).one_or_none()
    if not p or p.resource_id is None:
        flash("Item not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    res = Resource.query.filter(Resource.id == p.resource_id).one_or_none()
    if not res:
        flash("Resource not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    sub = Subscription.query.filter(Subscription.member_id == current_user.id).one_or_none()
    if sub is None:
        flash("No subscription found", "danger")
        return redirect(url_for('inventory.store', purchasable_id=purchasable_id))
    cid = sub.customerid

    # Collect items from form
    tracked, untracked = get_group_items(res.id)
    purchasable_lookup = {p.id: p for p in Purchasable.query.filter(Purchasable.resource_id == res.id).all()}
    items = []
    
    all_purchasables = tracked + untracked
    for t in all_purchasables:
        qty = int(request.form.get(f'qty_{t["id"]}', 0))
        if qty > 0:
            if t['current_qty'] is not None and qty > t['current_qty']:
                flash(f"Not enough {t['name']} in stock (have {t['current_qty']}, requested {qty})", "danger")
                return redirect(url_for('inventory.store', purchasable_id=purchasable_id))
            # Use the purchasable's own Stripe product code
            purch = purchasable_lookup.get(t['id'])
            item_product = None
            if purch and purch.product and purch.product.strip():
                item_product = purch.product.strip()
            if not item_product:
                flash(f"Error: No Stripe product code for {t['name']}", "danger")
                return redirect(url_for('inventory.store', purchasable_id=purchasable_id))
            items.append({'purchasable_id': t['id'], 'name': t['name'], 'qty': qty,
                          'unit_price': t['priceval'], 'current_qty': t['current_qty'],
                          'resource_id': res.id, 'product_code': item_product})

    if not items:
        flash("No items selected", "warning")
        return redirect(url_for('inventory.store', purchasable_id=purchasable_id))

    total_cents = sum(i['unit_price'] * i['qty'] for i in items)
    comment = request.form.get('comment', '').strip()

    # Validate total
    maxpurchase = float(current_app.config['globalConfig'].Config.get('Stripe','MaxPurchasable'))
    if total_cents <= 0:
        flash("Invalid total price", "danger")
        return redirect(url_for('inventory.store', purchasable_id=purchasable_id))
    if total_cents > maxpurchase:
        flash("Total price exceeds maximum allowable", "danger")
        return redirect(url_for('inventory.store', purchasable_id=purchasable_id))

    # --- Single Stripe Invoice ---
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','VendingToken')

    desc_parts = [f"{i['qty']}x {i['name']}" for i in items]
    invoice_desc = ", ".join(desc_parts)
    if comment:
        invoice_desc += f" ({comment})"

    try:
        invoice = stripe.Invoice.create(
            customer=cid,
            pending_invoice_items_behavior="exclude",
            description=invoice_desc
        )

        for i in items:
            line_amount = i['unit_price'] * i['qty']
            line_desc = f"{i['qty']}x {i['name']}"
            price = stripe.Price.create(
                unit_amount=line_amount,
                currency='usd',
                product=i['product_code'])
            stripe.InvoiceItem.create(
                customer=cid,
                price=price,
                description=line_desc,
                invoice=invoice.id)

        finalize = stripe.Invoice.finalize_invoice(invoice)
        if finalize['status'] == 'paid':
            pass
        elif finalize['status'] == 'open':
            pay = stripe.Invoice.pay(invoice)
            if pay['status'] != 'paid':
                flash("Payment was Declined", "danger")
                logger.warning("Stripe Payment declined for {0} productId {1}".format(current_user.member, product_code))
                return redirect(url_for('inventory.store', purchasable_id=purchasable_id))
        else:
            flash(f"Charge error: {finalize['status']}", "danger")
            logger.warning("Stripe Finalize error for {0} status {1}".format(current_user.member, finalize['status']))
            return redirect(url_for('inventory.store', purchasable_id=purchasable_id))
    except BaseException as e:
        flash(f"Stripe error: {e}", "danger")
        logger.warning("Stripe Payment error for {0}: {1}".format(current_user.member, e))
        return redirect(url_for('inventory.store', purchasable_id=purchasable_id))

    # --- Log individual items ---
    commentstr = f" ({comment})" if comment else ""
    for i in items:
        cost_str = f"${i['unit_price'] * i['qty'] / 100.0:0.2f}"
        # Only log into InventoryLog if the item was already tracked
        if i['current_qty'] is not None:
            old_qty = i['current_qty']
            new_qty = old_qty - i['qty']

            # Structured inventory journal
            il = InventoryLog(
                purchasable_id=i['purchasable_id'],
                resource_id=res.id,
                member_id=current_user.id,
                operation='purchase',
                quantity=i['qty'],
                unit_price=i['unit_price'],
                total_price=i['unit_price'] * i['qty'],
                old_quantity=old_qty,
                new_quantity=new_qty,
                comment=comment if comment else None
            )
            db.session.add(il)

        # Informational log event
        logmsg = f"Purchased {i['qty']}x {i['name']} for {cost_str}{commentstr}"
        authutil.log(eventtypes.RATTBE_LOGEVENT_PURCHASABLE_PURCHASE.id,
                     resource_id=res.id, member_id=current_user.id,
                     message=logmsg, commit=0)

    db.session.commit()

    # --- Single Slack message ---
    slack_chan = res.slack_admin_chan
    if slack_chan and slack_chan.strip():
        total_str = f"${total_cents / 100.0:0.2f}"
        slack_parts = [f"{i['qty']}x {i['name']}" for i in items]
        try:
            send_slack_message(slack_chan,
                f":moneybag: {current_user.firstname} {current_user.lastname} "
                f"purchased {', '.join(slack_parts)} for {total_str}{commentstr}")
        except:
            pass

    flash("Purchase successful!", "success")
    return redirect(url_for('inventory.store', purchasable_id=purchasable_id))


@blueprint.route('/group/<int:purchasable_id>/pull', methods=['POST'])
@login_required
def store_pull(purchasable_id):
    """Zero-cost pull from inventory. ARM only."""
    p = Purchasable.query.filter(Purchasable.id == purchasable_id).one_or_none()
    if not p or p.resource_id is None:
        flash("Item not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    res = Resource.query.filter(Resource.id == p.resource_id).one_or_none()
    if not res:
        flash("Resource not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    if not (current_user.is_specific_arm(resource_id=res.id) or current_user.privs('Admin')):
        flash("Permission denied", "danger")
        return redirect(url_for('inventory.store', purchasable_id=purchasable_id))

    tracked, _ = get_group_items(res.id)
    comment = request.form.get('comment', '').strip()
    commentstr = f" ({comment})" if comment else ""
    pulled_any = False

    for t in tracked:
        qty = int(request.form.get(f'pull_qty_{t["id"]}', 0))
        if qty > 0:
            old_qty = t['current_qty'] if t['current_qty'] is not None else 0
            new_qty = old_qty - qty

            il = InventoryLog(
                purchasable_id=t['id'],
                resource_id=res.id,
                member_id=current_user.id,
                operation='pull',
                quantity=qty,
                unit_price=0,
                total_price=0,
                old_quantity=old_qty,
                new_quantity=new_qty,
                comment=comment if comment else None
            )
            db.session.add(il)

            logmsg = f"Pulled {qty}x {t['name']}{commentstr}"
            authutil.log(eventtypes.RATTBE_LOGEVENT_INVENTORY_PULL.id,
                         resource_id=res.id, member_id=current_user.id,
                         message=logmsg, commit=0)
            pulled_any = True

    if pulled_any:
        db.session.commit()

        # Slack notification
        slack_chan = res.slack_admin_chan
        if slack_chan and slack_chan.strip():
            try:
                pull_parts = []
                for t in tracked:
                    qty = int(request.form.get(f'pull_qty_{t["id"]}', 0))
                    if qty > 0:
                        pull_parts.append(f"{qty}x {t['name']}")
                send_slack_message(slack_chan,
                    f":inbox_tray: {current_user.firstname} {current_user.lastname} "
                    f"pulled {', '.join(pull_parts)}{commentstr}")
            except:
                pass

        flash("Items pulled from inventory", "success")
    else:
        flash("No items selected", "warning")

    return redirect(url_for('inventory.store', purchasable_id=purchasable_id))


@blueprint.route('/group/<int:purchasable_id>/restock', methods=['POST'])
@login_required
def store_restock(purchasable_id):
    """Add inventory. ARM only."""
    p = Purchasable.query.filter(Purchasable.id == purchasable_id).one_or_none()
    if not p or p.resource_id is None:
        flash("Item not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    res = Resource.query.filter(Resource.id == p.resource_id).one_or_none()
    if not res:
        flash("Resource not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    if not (current_user.is_specific_arm(resource_id=res.id) or current_user.privs('Admin')):
        flash("Permission denied", "danger")
        return redirect(url_for('inventory.store', purchasable_id=purchasable_id))

    tracked, _ = get_group_items(res.id)
    comment = request.form.get('comment', '').strip()
    commentstr = f" ({comment})" if comment else ""
    restocked_any = False

    for t in tracked:
        qty = int(request.form.get(f'restock_qty_{t["id"]}', 0))
        if qty > 0:
            old_qty = t['current_qty'] if t['current_qty'] is not None else 0
            new_qty = old_qty + qty

            il = InventoryLog(
                purchasable_id=t['id'],
                resource_id=res.id,
                member_id=current_user.id,
                operation='restock',
                quantity=qty,
                unit_price=0,
                total_price=0,
                old_quantity=old_qty,
                new_quantity=new_qty,
                comment=comment if comment else None
            )
            db.session.add(il)

            logmsg = f"Restocked {qty}x {t['name']}{commentstr}"
            authutil.log(eventtypes.RATTBE_LOGEVENT_INVENTORY_RESTOCK.id,
                         resource_id=res.id, member_id=current_user.id,
                         message=logmsg, commit=0)
            restocked_any = True

    if restocked_any:
        db.session.commit()
        flash("Inventory restocked", "success")
    else:
        flash("No items selected", "warning")

    return redirect(url_for('inventory.store', purchasable_id=purchasable_id))


@blueprint.route('/group/<int:purchasable_id>/adjust', methods=['POST'])
@login_required
def store_adjust(purchasable_id):
    """Set absolute inventory count. ARM only."""
    p = Purchasable.query.filter(Purchasable.id == purchasable_id).one_or_none()
    if not p or p.resource_id is None:
        flash("Item not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    res = Resource.query.filter(Resource.id == p.resource_id).one_or_none()
    if not res:
        flash("Resource not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    if not (current_user.is_specific_arm(resource_id=res.id) or current_user.privs('Admin')):
        flash("Permission denied", "danger")
        return redirect(url_for('inventory.store', purchasable_id=purchasable_id))

    tracked, _ = get_group_items(res.id)
    comment = request.form.get('comment', '').strip()
    commentstr = f" ({comment})" if comment else ""
    adjusted_any = False

    for t in tracked:
        adj_str = request.form.get(f'adjust_qty_{t["id"]}', '').strip()
        if adj_str == '':
            continue
        try:
            new_qty = int(adj_str)
        except ValueError:
            continue

        old_qty = t['current_qty'] if t['current_qty'] is not None else 0
        if new_qty == old_qty:
            continue

        il = InventoryLog(
            purchasable_id=t['id'],
            resource_id=res.id,
            member_id=current_user.id,
            operation='adjust',
            quantity=abs(new_qty - old_qty),
            unit_price=0,
            total_price=0,
            old_quantity=old_qty,
            new_quantity=new_qty,
            comment=comment if comment else None
        )
        db.session.add(il)

        logmsg = f"Adjusted {t['name']} from {old_qty} to {new_qty}{commentstr}"
        authutil.log(eventtypes.RATTBE_LOGEVENT_INVENTORY_ADJUST.id,
                     resource_id=res.id, member_id=current_user.id,
                     message=logmsg, commit=0)
        adjusted_any = True

    if adjusted_any:
        db.session.commit()
        flash("Inventory adjusted", "success")
    else:
        flash("No changes made", "warning")

    return redirect(url_for('inventory.store', purchasable_id=purchasable_id))


@blueprint.route('/group/<int:purchasable_id>/init', methods=['POST'])
@login_required
def store_init(purchasable_id):
    """Set initial inventory for untracked items. ARM only."""
    p = Purchasable.query.filter(Purchasable.id == purchasable_id).one_or_none()
    if not p or p.resource_id is None:
        flash("Item not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    res = Resource.query.filter(Resource.id == p.resource_id).one_or_none()
    if not res:
        flash("Resource not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    if not (current_user.is_specific_arm(resource_id=res.id) or current_user.privs('Admin')):
        flash("Permission denied", "danger")
        return redirect(url_for('inventory.store', purchasable_id=purchasable_id))

    _, untracked = get_group_items(res.id)
    comment = request.form.get('comment', '').strip()
    commentstr = f" ({comment})" if comment else ""
    init_any = False

    for t in untracked:
        qty_str = request.form.get(f'init_qty_{t["id"]}', '').strip()
        if qty_str == '':
            continue
        try:
            qty = int(qty_str)
        except ValueError:
            continue
        if qty < 0:
            continue

        il = InventoryLog(
            purchasable_id=t['id'],
            resource_id=res.id,
            member_id=current_user.id,
            operation='adjust',
            quantity=qty,
            unit_price=0,
            total_price=0,
            old_quantity=0,
            new_quantity=qty,
            comment=f"Initial inventory{' - ' + comment if comment else ''}"
        )
        db.session.add(il)

        logmsg = f"Set initial inventory for {t['name']}: {qty}{commentstr}"
        authutil.log(eventtypes.RATTBE_LOGEVENT_INVENTORY_ADJUST.id,
                     resource_id=res.id, member_id=current_user.id,
                     message=logmsg, commit=0)
        init_any = True

    if init_any:
        db.session.commit()
        flash("Initial inventory set", "success")
    else:
        flash("No items initialized", "warning")

    return redirect(url_for('inventory.store', purchasable_id=purchasable_id))


@blueprint.route('/group/<int:purchasable_id>/report', methods=['GET'])
@login_required
def store_report(purchasable_id):
    """Inventory report for a resource group."""
    p = Purchasable.query.filter(Purchasable.id == purchasable_id).one_or_none()
    if not p or p.resource_id is None:
        flash("Item not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    res = Resource.query.filter(Resource.id == p.resource_id).one_or_none()
    if not res:
        flash("Resource not found", "danger")
        return redirect(url_for('purchasables.purchasables'))

    if not (current_user.is_specific_arm(resource_id=res.id) or current_user.privs('Admin', 'Finance')):
        flash("Permission denied", "danger")
        return redirect(url_for('inventory.store', purchasable_id=purchasable_id))

    # Get all inventory log entries for this resource
    entries = InventoryLog.query.filter(
        InventoryLog.resource_id == res.id
    ).order_by(InventoryLog.time_logged.desc()).all()

    # Build member name lookup
    member_ids = set(e.member_id for e in entries if e.member_id)
    members = {}
    if member_ids:
        for m in Member.query.filter(Member.id.in_(member_ids)).all():
            members[m.id] = f"{m.firstname} {m.lastname}"

    # Build purchasable name lookup
    purchasable_ids = set(e.purchasable_id for e in entries if e.purchasable_id)
    purch_names = {}
    if purchasable_ids:
        for pp in Purchasable.query.filter(Purchasable.id.in_(purchasable_ids)).all():
            purch_names[pp.id] = pp.name

    # Compute summary per item
    tracked, _ = get_group_items(res.id)
    summary = {}
    for t in tracked:
        tid = t['id']
        item_entries = [e for e in entries if e.purchasable_id == tid]
        sold = sum(e.quantity for e in item_entries if e.operation == 'purchase')
        pulled = sum(e.quantity for e in item_entries if e.operation == 'pull')
        restocked = sum(e.quantity for e in item_entries if e.operation == 'restock')
        revenue = sum(e.total_price for e in item_entries if e.operation == 'purchase' and e.total_price)
        summary[tid] = {
            'name': t['name'],
            'current_qty': t['current_qty'],
            'sold': sold,
            'pulled': pulled,
            'restocked': restocked,
            'revenue': revenue,
            'revenue_str': f"${revenue/100.0:0.2f}" if revenue else "$0.00",
        }

    eastern = dateutil.tz.gettz('US/Eastern')
    utc = dateutil.tz.gettz('UTC')
    # Format entries for display
    detail = []
    for e in entries:
        d = {}
        if e.time_logged:
            d['datetime'] = e.time_logged.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None)
            d['datestr'] = d['datetime'].strftime("%b %d %H:%M")
        else:
            d['datestr'] = ""
        d['item'] = purch_names.get(e.purchasable_id, f"Item #{e.purchasable_id}")
        d['operation'] = e.operation
        d['quantity'] = e.quantity
        d['price_str'] = f"${e.total_price/100.0:0.2f}" if e.total_price and e.total_price > 0 else ""
        d['old_qty'] = e.old_quantity
        d['new_qty'] = e.new_quantity
        d['stock_change'] = f"{e.old_quantity} → {e.new_quantity}"
        d['member'] = members.get(e.member_id, f"#{e.member_id}" if e.member_id else "")
        d['comment'] = e.comment or ""
        detail.append(d)

    return render_template('store_report.html',
        resource=res,
        summary=summary,
        detail=detail,
        purchasable_id=purchasable_id)


def register_pages(app):
    app.register_blueprint(blueprint)
