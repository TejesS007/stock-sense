from flask import Blueprint, render_template
from models import StockMove
from .auth import login_required

move_history_bp = Blueprint('move_history', __name__, url_prefix='/move-history')


@move_history_bp.route('/')
@login_required
def index():
    # All move types, most recent first. Template explodes each move into
    # one ledger row per line (a single reference with N products -> N rows).
    moves = StockMove.query.order_by(StockMove.created_at.desc()).all()
    return render_template('move_history/index.html', moves=moves)
