from datetime import datetime, timezone
from app import create_app
from models import db, User, Product, Stock
from inventory_utils import get_default_warehouse, get_default_location

app = create_app({
    'TESTING': True,
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    'WTF_CSRF_ENABLED': False
})

client = app.test_client()

with app.app_context():
    db.create_all()

    user = User(login_id='opsuser', email='ops@stocksense.com')
    user.set_password('opspass')
    db.session.add(user)

    warehouse = get_default_warehouse()
    loc_a = get_default_location()

    prod = Product(name='Steel Rod', sku='ROD-01', uom='Units', reorder_point=5.0)
    db.session.add(prod)
    db.session.commit()

    # Seed 10 units on hand at loc_a
    db.session.add(Stock(product_id=prod.id, location_id=loc_a.id, on_hand=10.0, reserved=0.0))
    db.session.commit()

    client.post('/auth/login', data={'login_id': 'opsuser', 'password': 'opspass'})

    print("--- 1. Delivery: request MORE than free_to_use -> Waiting ---")
    resp = client.post('/operations/delivery/new', data={
        'contact': 'Big Customer', 'from_location_id': str(loc_a.id),
        'schedule_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'product_id[]': [str(prod.id)], 'quantity[]': ['25']
    }, follow_redirects=False)
    assert resp.status_code == 302
    from models import StockMove
    move = StockMove.query.filter_by(contact='Big Customer').first()
    assert move.status == 'Draft'

    client.post(f'/operations/delivery/{move.id}/validate')
    db.session.refresh(move)
    assert move.status == 'Waiting', f"Expected Waiting, got {move.status}"
    print("Correctly went to Waiting when qty > free_to_use!")

    print("--- 2. Delivery: within free_to_use -> Ready -> Done, stock decrements ---")
    resp2 = client.post('/operations/delivery/new', data={
        'contact': 'Small Customer', 'from_location_id': str(loc_a.id),
        'schedule_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'product_id[]': [str(prod.id)], 'quantity[]': ['4']
    }, follow_redirects=False)
    move2 = StockMove.query.filter_by(contact='Small Customer').first()
    client.post(f'/operations/delivery/{move2.id}/validate')
    db.session.refresh(move2)
    assert move2.status == 'Ready', f"Expected Ready, got {move2.status}"
    client.post(f'/operations/delivery/{move2.id}/validate')
    db.session.refresh(move2)
    assert move2.status == 'Done'
    stock = Stock.query.filter_by(product_id=prod.id, location_id=loc_a.id).first()
    assert stock.on_hand == 6.0, f"Expected 6.0 after -4 delivery, got {stock.on_hand}"
    print("Delivery Draft->Ready->Done decremented stock correctly (10 -> 6)!")

    print("--- 3. Internal Transfer: Draft -> Done moves stock between two locations ---")
    from models import Location
    loc_b = Location(name='Rack B', short_code='RACKB', warehouse_id=warehouse.id)
    db.session.add(loc_b)
    db.session.commit()

    resp3 = client.post('/operations/transfers/new', data={
        'from_location_id': str(loc_a.id), 'to_location_id': str(loc_b.id),
        'schedule_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'product_id[]': [str(prod.id)], 'quantity[]': ['3']
    }, follow_redirects=False)
    assert resp3.status_code == 302
    transfer = StockMove.query.filter_by(type='INTERNAL').first()
    assert transfer.status == 'Draft'

    client.post(f'/operations/transfers/{transfer.id}/validate')
    db.session.refresh(transfer)
    assert transfer.status == 'Done'

    stock_a = Stock.query.filter_by(product_id=prod.id, location_id=loc_a.id).first()
    stock_b = Stock.query.filter_by(product_id=prod.id, location_id=loc_b.id).first()
    assert stock_a.on_hand == 3.0, f"Expected loc_a at 3.0 (6-3), got {stock_a.on_hand}"
    assert stock_b.on_hand == 3.0, f"Expected loc_b at 3.0, got {stock_b.on_hand}"
    print("Internal Transfer moved 3 units between locations correctly!")

print("\n=== DELIVERY & TRANSFER LOGIC TESTS PASSED ===")
print("NOTE: stock.py adjust, settings.py CRUD, and dashboard.py KPIs are")
print("implemented but not covered here — write test_stock.py / test_settings.py")
print("following this same pattern before you trust them in a demo.")
