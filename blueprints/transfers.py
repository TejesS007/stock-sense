from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from models import db, StockMove, StockMoveLine, Product, Location, Warehouse, Stock, User
from inventory_utils import get_default_warehouse, get_default_location, generate_move_reference
from .auth import login_required

transfers_bp = Blueprint('transfers', __name__, url_prefix='/operations/transfers')


@transfers_bp.route('/')
@login_required
def index():
    moves = StockMove.query.filter_by(type='INTERNAL').order_by(StockMove.created_at.desc()).all()
    return render_template('transfers/index.html', moves=moves)


@transfers_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create():
    locations = Location.query.order_by(Location.warehouse_id, Location.name).all()
    if not locations:
        locations = [get_default_location()]
    warehouse = locations[0].warehouse if (locations and locations[0].warehouse) else get_default_warehouse()
    products = Product.query.order_by(Product.name).all()
    user = g.user or (db.session.get(User, session.get('user_id')) if session.get('user_id') else None)

    if request.method == 'POST':
        schedule_date_str = request.form.get('schedule_date', '').strip()
        from_location_id_str = request.form.get('from_location_id', '').strip()
        to_location_id_str = request.form.get('to_location_id', '').strip()

        errors = {}
        if not (from_location_id_str.isdigit() and to_location_id_str.isdigit()):
            errors['location'] = 'Both source and destination locations are required.'
        elif from_location_id_str == to_location_id_str:
            errors['location'] = 'Source and destination locations must be different.'

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
            errors['lines'] = 'Please add at least one product with a valid quantity > 0.'

        if errors:
            for msg in errors.values():
                flash(msg, 'error')
            auto_ref = generate_move_reference(warehouse.id, 'INTERNAL')
            return render_template(
                'transfers/create.html', warehouse=warehouse, locations=locations, products=products,
                responsible_user=user, auto_ref=auto_ref,
                today=datetime.now(timezone.utc).strftime('%Y-%m-%d'), form_data=request.form
            ), 400

        target_warehouse_id = warehouse.id
        if from_location_id_str.isdigit():
            chosen_loc = db.session.get(Location, int(from_location_id_str))
            if chosen_loc and chosen_loc.warehouse_id:
                target_warehouse_id = chosen_loc.warehouse_id

        reference = generate_move_reference(target_warehouse_id, 'INTERNAL')
        move = StockMove(
            reference=reference, type='INTERNAL',
            from_location_id=int(from_location_id_str), to_location_id=int(to_location_id_str),
            contact=None, schedule_date=schedule_date, status='Draft',
            responsible_user_id=session.get('user_id'),
        )
        db.session.add(move)
        db.session.flush()

        for pid, qty in parsed_lines:
            db.session.add(StockMoveLine(move_id=move.id, product_id=pid, quantity=qty))

        db.session.commit()
        flash(f'Internal Transfer {move.reference} created as Draft.', 'success')
        return redirect(url_for('transfers.detail', id=move.id))

    auto_ref = generate_move_reference(warehouse.id, 'INTERNAL')
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    return render_template('transfers/create.html', warehouse=warehouse, locations=locations, products=products,
                            responsible_user=user, auto_ref=auto_ref, today=today_str, form_data={})


@transfers_bp.route('/<int:id>')
@login_required
def detail(id):
    move = db.session.get(StockMove, id)
    if not move or move.type != 'INTERNAL':
        flash('Internal Transfer not found.', 'error')
        return redirect(url_for('transfers.index'))
    return render_template('transfers/detail.html', move=move)


@transfers_bp.route('/<int:id>/validate', methods=['POST'])
@login_required
def validate(id):
    move = db.session.get(StockMove, id)
    if not move or move.type != 'INTERNAL':
        flash('Internal Transfer not found.', 'error')
        return redirect(url_for('transfers.index'))

    if move.status != 'Draft':
        flash(f'Cannot validate move in status {move.status}.', 'warning')
        return redirect(url_for('transfers.detail', id=move.id))

    for line in move.lines:
        from_stock = Stock.query.filter_by(product_id=line.product_id, location_id=move.from_location_id).first()
        if from_stock:
            from_stock.on_hand -= line.quantity
        else:
            from_stock = Stock(product_id=line.product_id, location_id=move.from_location_id,
                                on_hand=-line.quantity, reserved=0.0)
            db.session.add(from_stock)

        to_stock = Stock.query.filter_by(product_id=line.product_id, location_id=move.to_location_id).first()
        if to_stock:
            to_stock.on_hand += line.quantity
        else:
            db.session.add(Stock(product_id=line.product_id, location_id=move.to_location_id,
                                  on_hand=line.quantity, reserved=0.0))

    move.status = 'Done'
    db.session.commit()
    flash(f'Internal Transfer {move.reference} validated and Done. Stock moved between locations.', 'success')
    return redirect(url_for('transfers.detail', id=move.id))


@transfers_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
def cancel(id):
    move = db.session.get(StockMove, id)
    if not move or move.type != 'INTERNAL':
        flash('Internal Transfer not found.', 'error')
        return redirect(url_for('transfers.index'))

    if move.status == 'Draft':
        move.status = 'Canceled'
        db.session.commit()
        flash(f'Internal Transfer {move.reference} has been canceled. Stock was not modified.', 'info')
    elif move.status == 'Done':
        flash('Validated (Done) moves cannot be canceled.', 'warning')
    else:
        flash(f'Move is already {move.status}.', 'info')

    return redirect(url_for('transfers.detail', id=move.id))
