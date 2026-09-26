from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    login_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    reset_otp = db.Column(db.String(6), nullable=True)
    reset_otp_expiry = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.login_id}>'


class Warehouse(db.Model):
    __tablename__ = 'warehouses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    short_code = db.Column(db.String(20), unique=True, nullable=False)
    address = db.Column(db.String(255), nullable=True)

    locations = db.relationship('Location', backref='warehouse', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Warehouse {self.short_code}: {self.name}>'


class Location(db.Model):
    __tablename__ = 'locations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    short_code = db.Column(db.String(20), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)

    def __repr__(self):
        return f'<Location {self.short_code}: {self.name}>'


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    products = db.relationship('Product', backref='category', lazy=True)

    def __repr__(self):
        return f'<Category {self.name}>'


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    sku = db.Column(db.String(50), unique=True, nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    uom = db.Column(db.String(20), nullable=False, default='Units')
    reorder_point = db.Column(db.Float, nullable=False, default=0.0)

    stock_records = db.relationship('Stock', backref='product', lazy=True, cascade='all, delete-orphan')

    @property
    def total_on_hand(self):
        return sum(s.on_hand for s in self.stock_records) if self.stock_records else 0.0

    @property
    def is_low_stock(self):
        return self.total_on_hand < self.reorder_point

    def __repr__(self):
        return f'<Product {self.sku}: {self.name}>'


class Stock(db.Model):
    __tablename__ = 'stocks'

    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), primary_key=True)
    on_hand = db.Column(db.Float, nullable=False, default=0.0)
    reserved = db.Column(db.Float, nullable=False, default=0.0)

    location = db.relationship('Location', backref='stock_records', lazy=True)

    @property
    def free_to_use(self):
        return self.on_hand - self.reserved

    def __repr__(self):
        return f'<Stock P:{self.product_id} L:{self.location_id} OnHand:{self.on_hand} Reserved:{self.reserved}>'


class StockMove(db.Model):
    __tablename__ = 'stock_moves'

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(64), unique=True, nullable=True, index=True)
    type = db.Column(db.String(20), nullable=False)  # IN, OUT, INTERNAL, ADJUSTMENT
    from_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    to_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    contact = db.Column(db.String(150), nullable=True)
    schedule_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Draft')  # Draft, Waiting, Ready, Done, Canceled
    responsible_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    from_location = db.relationship('Location', foreign_keys=[from_location_id], backref='outgoing_moves')
    to_location = db.relationship('Location', foreign_keys=[to_location_id], backref='incoming_moves')
    responsible_user = db.relationship('User', foreign_keys=[responsible_user_id], backref='managed_moves')
    lines = db.relationship('StockMoveLine', backref='move', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<StockMove {self.reference} ({self.type}) - {self.status}>'


class StockMoveLine(db.Model):
    __tablename__ = 'stock_move_lines'

    id = db.Column(db.Integer, primary_key=True)
    move_id = db.Column(db.Integer, db.ForeignKey('stock_moves.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=1.0)

    product = db.relationship('Product', backref='move_lines', lazy=True)

    def __repr__(self):
        return f'<StockMoveLine Move:{self.move_id} Product:{self.product_id} Qty:{self.quantity}>'
