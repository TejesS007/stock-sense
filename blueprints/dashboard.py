from datetime import datetime, timezone
from flask import Blueprint, render_template
from models import Product, StockMove
from .auth import login_required

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@login_required
def index():
    today = datetime.now(timezone.utc).date()
    products = Product.query.all()

    total_products = len(products)
    low_stock_count = sum(1 for p in products if p.total_on_hand < p.reorder_point)
    out_of_stock_count = sum(1 for p in products if p.total_on_hand <= 0)

    def ops_summary(move_type, actionable_statuses):
        moves = StockMove.query.filter_by(type=move_type).all()
        actionable = [m for m in moves if m.status in actionable_statuses]
        late = [m for m in actionable if m.schedule_date and m.schedule_date < today]
        return {
            'to_action': len(actionable),
            'late': len(late),
            'total': len(moves),
        }

    receipts_summary = ops_summary('IN', ('Draft', 'Ready'))
    delivery_summary = ops_summary('OUT', ('Draft', 'Waiting', 'Ready'))
    transfers_scheduled = len([
        m for m in StockMove.query.filter_by(type='INTERNAL').all() if m.status == 'Draft'
    ])

    return render_template(
        'dashboard/index.html',
        total_products=total_products,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        receipts_summary=receipts_summary,
        delivery_summary=delivery_summary,
        transfers_scheduled=transfers_scheduled,
    )
