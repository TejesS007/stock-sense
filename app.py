import os
from flask import Flask, session, g
from models import db, User
from blueprints import (
    auth_bp,
    dashboard_bp,
    products_bp,
    stock_bp,
    receipts_bp,
    delivery_bp,
    transfers_bp,
    move_history_bp,
    settings_bp,
)


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=False)

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dayflow.db')
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'stocksense-inventory-secret-key-2026'),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', f'sqlite:///{db_path}'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    @app.before_request
    def load_logged_in_user():
        user_id = session.get('user_id')
        if user_id is None:
            g.user = None
        else:
            g.user = db.session.get(User, user_id)

    @app.context_processor
    def inject_current_user():
        return {
            'current_user': g.get('user'),
            'logged_in': g.get('user') is not None
        }

    # Register blueprints
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(receipts_bp)
    app.register_blueprint(delivery_bp)
    app.register_blueprint(transfers_bp)
    app.register_blueprint(move_history_bp)
    app.register_blueprint(settings_bp)

    with app.app_context():
        db.create_all()

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
