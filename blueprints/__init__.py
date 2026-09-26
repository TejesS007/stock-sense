from .auth import auth_bp, login_required
from .dashboard import dashboard_bp
from .products import products_bp
from .stock import stock_bp
from .receipts import receipts_bp
from .delivery import delivery_bp
from .transfers import transfers_bp
from .move_history import move_history_bp
from .settings import settings_bp

__all__ = [
    'auth_bp',
    'login_required',
    'dashboard_bp',
    'products_bp',
    'stock_bp',
    'receipts_bp',
    'delivery_bp',
    'transfers_bp',
    'move_history_bp',
    'settings_bp',
]
