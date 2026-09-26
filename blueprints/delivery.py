from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from models import db, StockMove, StockMoveLine, Product, Location, Stock, User
from inventory_utils import get_default_warehouse, get_default_location, generate_move_reference
from .auth import login_required

delivery_bp = Blueprint('delivery', __name__, url_prefix='/operations/delivery')


@delivery_bp.route('/')
@login_required
def index():
    moves = StockMove.query.filter_by(type='OUT').order_by(StockMove.created_at.desc()).all()
    return render_template('delivery/index.html', moves=moves)


@delivery_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create():
    locations = Location.query.order_by(Location.warehouse_id, Location.name).all()
    if not locations:
        locations = [get_default_location()]
    warehouse = locations[0].warehouse if (locations and locations[0].warehouse) else get_default_warehouse()
    products = Product.query.order_by(Product.name).all()
    user = g.user or (db.session.get(User, session.get('user_id')) if session.get('user_id') else None)

    if request.method == 'POST':
        contact = request.form.get('contact', '').strip()
        schedule_date_str = request.form.get('schedule_date', '').strip()
        from_location_id_str = request.form.get('from_location_id', '').strip()

        if from_location_id_str and from_location_id_str.isdigit():
            from_location_id = int(from_location_id_str)
        else:
            from_location_id = locations[0].id if locations else get_default_location().id

        if schedule_date_str:
            try:
                schedule_date = datetime.strptime(schedule_date_str, '%Y-%m-%d').date()
            except ValueError:
                schedule_date = datetime.now(timezone.utc).date()
        else:
            schedule_date = datetime.now(timezone.utc).date()

        product_ids = request.form.getlist('product_id[]') or request.form.getlist('product_id')
        quantities = request.form.getlist('quantity[]') or request.form.getlist('quantity')

        parsed_lines = []
        for p_id_str, qty_str in zip(product_ids, quantities):
            if p_id_str and p_id_str.isdigit():
                try:
                    qty = float(qty_str)
                    if qty > 0:
                        parsed_lines.append((int(p_id_str), qty))
                except (ValueError, TypeError):
                    continue

        if not parsed_lines:
            flash('Please add at least one product with a valid quantity > 0.', 'error')
            auto_ref = generate_move_reference(warehouse.id, 'OUT')
            return render_template(
                'delivery/create.html', warehouse=warehouse, locations=locations, products=products,
                responsible_user=user, auto_ref=auto_ref,
                today=datetime.now(timezone.utc).strftime('%Y-%m-%d'), form_data=request.form
            ), 400

        target_warehouse_id = warehouse.id
        if from_location_id:
            chosen_loc = db.session.get(Location, from_location_id)
            if chosen_loc and chosen_loc.warehouse_id:
                target_warehouse_id = chosen_loc.warehouse_id

        reference = generate_move_reference(target_warehouse_id, 'OUT')
        move = StockMove(
            reference=reference, type='OUT', from_location_id=from_location_id, to_location_id=None,
            contact=contact or 'Customer', schedule_date=schedule_date, status='Draft',
            responsible_user_id=session.get('user_id'),
        )
        db.session.add(move)
        db.session.flush()

        for pid, qty in parsed_lines:
            db.session.add(StockMoveLine(move_id=move.id, product_id=pid, quantity=qty))

        db.session.commit()
        flash(f'Delivery {move.reference} created as Draft.', 'success')
        return redirect(url_for('delivery.detail', id=move.id))

    auto_ref = generate_move_reference(warehouse.id, 'OUT')
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    return render_template('delivery/create.html', warehouse=warehouse, locations=locations, products=products,
                            responsible_user=user, auto_ref=auto_ref, today=today_str, form_data={})


@delivery_bp.route('/<int:id>')
@login_required
def detail(id):
    move = db.session.get(StockMove, id)
    if not move or move.type != 'OUT':
        flash('Delivery not found.', 'error')
        return redirect(url_for('delivery.index'))
    return render_template('delivery/detail.html', move=move)


def _line_shortfalls(move):
    """Return list of (line, available) for lines where free_to_use is insufficient."""
    shortfalls = []
    for line in move.lines:
        stock = Stock.query.filter_by(product_id=line.product_id, location_id=move.from_location_id).first()
        available = stock.free_to_use if stock else 0.0
        if line.quantity > available:
            shortfalls.append((line, available))
    return shortfalls


@delivery_bp.route('/<int:id>/validate', methods=['POST'])
@login_required
def validate(id):
    move = db.session.get(StockMove, id)
    if not move or move.type != 'OUT':
        flash('Delivery not found.', 'error')
        return redirect(url_for('delivery.index'))

    if move.status in ('Draft', 'Waiting'):
        shortfalls = _line_shortfalls(move)
        if shortfalls:
            move.status = 'Waiting'
            db.session.commit()
            names = ', '.join(f'{l.product.name} (need {l.quantity:g}, have {a:g})' for l, a in shortfalls)
            flash(f'Delivery {move.reference} is Waiting — insufficient stock: {names}.', 'warning')
        else:
            move.status = 'Ready'
            db.session.commit()
            flash(f'Delivery {move.reference} status updated to Ready.', 'info')
    elif move.status == 'Ready':
        shortfalls = _line_shortfalls(move)
        if shortfalls:
            move.status = 'Waiting'
            db.session.commit()
            flash(f'Delivery {move.reference} moved back to Waiting — stock changed since Ready.', 'warning')
        else:
            for line in move.lines:
                stock = Stock.query.filter_by(product_id=line.product_id, location_id=move.from_location_id).first()
                stock.on_hand -= line.quantity
            move.status = 'Done'
            db.session.commit()
            flash(f'Delivery {move.reference} validated and Done. Stock levels updated.', 'success')
    else:
        flash(f'Cannot validate move in status {move.status}.', 'warning')

    return redirect(url_for('delivery.detail', id=move.id))


@delivery_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
def cancel(id):
    move = db.session.get(StockMove, id)
    if not move or move.type != 'OUT':
        flash('Delivery not found.', 'error')
        return redirect(url_for('delivery.index'))

    if move.status in ('Draft', 'Waiting', 'Ready'):
        move.status = 'Canceled'
        db.session.commit()
        flash(f'Delivery {move.reference} has been canceled. Stock was not modified.', 'info')
    elif move.status == 'Done':
        flash('Validated (Done) moves cannot be canceled.', 'warning')
    else:
        flash(f'Move is already {move.status}.', 'info')

    return redirect(url_for('delivery.detail', id=move.id))
