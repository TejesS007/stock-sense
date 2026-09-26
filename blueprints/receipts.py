from datetime import datetime, timezone, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from models import db, StockMove, StockMoveLine, Product, Location, Warehouse, Stock, User
from inventory_utils import get_default_warehouse, get_default_location, generate_move_reference
from .auth import login_required

receipts_bp = Blueprint('receipts', __name__, url_prefix='/operations/receipts')


@receipts_bp.route('/')
@login_required
def index():
    moves = StockMove.query.filter_by(type='IN').order_by(StockMove.created_at.desc()).all()
    return render_template('receipts/index.html', moves=moves)


@receipts_bp.route('/new', methods=['GET', 'POST'])
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
        to_location_id_str = request.form.get('to_location_id', '').strip()

        # Parse destination location
        if to_location_id_str and to_location_id_str.isdigit():
            to_location_id = int(to_location_id_str)
        else:
            to_location_id = locations[0].id if locations else get_default_location().id

        # Parse schedule date
        schedule_date = None
        if schedule_date_str:
            try:
                schedule_date = datetime.strptime(schedule_date_str, '%Y-%m-%d').date()
            except ValueError:
                schedule_date = datetime.now(timezone.utc).date()
        else:
            schedule_date = datetime.now(timezone.utc).date()

        # Parse line items
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
            auto_ref = generate_move_reference(warehouse.id, 'IN')
            return render_template(
                'receipts/create.html',
                warehouse=warehouse,
                locations=locations,
                products=products,
                responsible_user=user,
                auto_ref=auto_ref,
                today=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                form_data=request.form
            ), 400

        target_warehouse_id = warehouse.id
        if to_location_id:
            chosen_loc = db.session.get(Location, to_location_id)
            if chosen_loc and chosen_loc.warehouse_id:
                target_warehouse_id = chosen_loc.warehouse_id

        # Auto-generate reference format WH<warehouse_id>/IN/<seq>
        reference = generate_move_reference(target_warehouse_id, 'IN')

        move = StockMove(
            reference=reference,
            type='IN',
            from_location_id=None,
            to_location_id=to_location_id,
            contact=contact or 'Vendor',
            schedule_date=schedule_date,
            status='Draft',
            responsible_user_id=session.get('user_id')
        )
        db.session.add(move)
        db.session.flush()

        for pid, qty in parsed_lines:
            line = StockMoveLine(
                move_id=move.id,
                product_id=pid,
                quantity=qty
            )
            db.session.add(line)

        db.session.commit()
        flash(f'Receipt {move.reference} created as Draft.', 'success')
        return redirect(url_for('receipts.detail', id=move.id))

    # GET request
    auto_ref = generate_move_reference(warehouse.id, 'IN')
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    return render_template(
        'receipts/create.html',
        warehouse=warehouse,
        locations=locations,
        products=products,
        responsible_user=user,
        auto_ref=auto_ref,
        today=today_str,
        form_data={}
    )


@receipts_bp.route('/<int:id>')
@login_required
def detail(id):
    move = db.session.get(StockMove, id)
    if not move or move.type != 'IN':
        flash('Receipt not found.', 'error')
        return redirect(url_for('receipts.index'))

    return render_template('receipts/detail.html', move=move)


@receipts_bp.route('/<int:id>/validate', methods=['POST'])
@login_required
def validate(id):
    move = db.session.get(StockMove, id)
    if not move or move.type != 'IN':
        flash('Receipt not found.', 'error')
        return redirect(url_for('receipts.index'))

    if move.status == 'Draft':
        move.status = 'Ready'
        db.session.commit()
        flash(f'Receipt {move.reference} status updated to Ready.', 'info')
    elif move.status == 'Ready':
        # Ready -> Done: Atomically apply stock delta to destination location
        dest_loc_id = move.to_location_id or get_default_location().id

        for line in move.lines:
            stock = Stock.query.filter_by(
                product_id=line.product_id,
                location_id=dest_loc_id
            ).first()

            if stock:
                stock.on_hand += line.quantity
            else:
                stock = Stock(
                    product_id=line.product_id,
                    location_id=dest_loc_id,
                    on_hand=line.quantity,
                    reserved=0.0
                )
                db.session.add(stock)

        move.status = 'Done'
        db.session.commit()
        flash(f'Receipt {move.reference} validated and Done. Stock levels updated.', 'success')
    else:
        flash(f'Cannot validate move in status {move.status}.', 'warning')

    return redirect(url_for('receipts.detail', id=move.id))


@receipts_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
def cancel(id):
    move = db.session.get(StockMove, id)
    if not move or move.type != 'IN':
        flash('Receipt not found.', 'error')
        return redirect(url_for('receipts.index'))

    if move.status in ['Draft', 'Ready', 'Waiting']:
        # Cancel never touches stock
        move.status = 'Canceled'
        db.session.commit()
        flash(f'Receipt {move.reference} has been canceled. Stock was not modified.', 'info')
    elif move.status == 'Done':
        flash('Validated (Done) moves cannot be canceled.', 'warning')
    else:
        flash(f'Move is already {move.status}.', 'info')

    return redirect(url_for('receipts.detail', id=move.id))
