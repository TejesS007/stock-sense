from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, Stock, Product, Location, StockMove, StockMoveLine
from inventory_utils import get_default_location, generate_move_reference
from .auth import login_required

stock_bp = Blueprint('stock', __name__, url_prefix='/stock')


def _rows():
    """One row per (product, location) that currently has a Stock record,
    plus one zero row for any product that has none yet, at the default location."""
    rows = []
    seen_products = set()
    for stock in Stock.query.join(Product).order_by(Product.name).all():
        rows.append(stock)
        seen_products.add(stock.product_id)

    default_loc = get_default_location()
    for product in Product.query.order_by(Product.name).all():
        if product.id not in seen_products:
            placeholder = Stock(product_id=product.id, location_id=default_loc.id, on_hand=0.0, reserved=0.0)
            placeholder.product = product
            placeholder.location = default_loc
            rows.append(placeholder)
    return rows


@stock_bp.route('/')
@login_required
def index():
    return render_template('stock/index.html', rows=_rows())


@stock_bp.route('/adjust', methods=['POST'])
@login_required
def adjust():
    product_id_str = request.form.get('product_id', '').strip()
    location_id_str = request.form.get('location_id', '').strip()
    new_qty_str = request.form.get('new_quantity', '').strip()

    if not (product_id_str.isdigit() and location_id_str.isdigit()):
        flash('Invalid product or location.', 'error')
        return redirect(url_for('stock.index'))

    product_id = int(product_id_str)
    location_id = int(location_id_str)
    location = db.session.get(Location, location_id)
    product = db.session.get(Product, product_id)

    if not location or not product:
        flash('Product or location not found.', 'error')
        return redirect(url_for('stock.index'))

    try:
        new_qty = float(new_qty_str)
        if new_qty < 0:
            raise ValueError
    except (ValueError, TypeError):
        flash('Counted quantity must be a valid non-negative number.', 'error')
        return redirect(url_for('stock.index'))

    stock = Stock.query.filter_by(product_id=product_id, location_id=location_id).first()
    current_on_hand = stock.on_hand if stock else 0.0
    delta = new_qty - current_on_hand

    if delta == 0:
        flash('No change in counted quantity — nothing to adjust.', 'info')
        return redirect(url_for('stock.index'))

    reference = generate_move_reference(location.warehouse_id, 'ADJUSTMENT')
    move = StockMove(
        reference=reference,
        type='ADJUSTMENT',
        from_location_id=None,
        to_location_id=location_id,
        contact='Stock Count',
        schedule_date=datetime.now(timezone.utc).date(),
        status='Done',
        responsible_user_id=session.get('user_id'),
    )
    db.session.add(move)
    db.session.flush()

    db.session.add(StockMoveLine(move_id=move.id, product_id=product_id, quantity=delta))

    if stock:
        stock.on_hand = new_qty
    else:
        db.session.add(Stock(product_id=product_id, location_id=location_id, on_hand=new_qty, reserved=0.0))

    db.session.commit()
    flash(f'Stock adjusted for "{product.name}": {current_on_hand:g} → {new_qty:g} ({reference}).', 'success')
    return redirect(url_for('stock.index'))
