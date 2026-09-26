import sys
from datetime import datetime, timezone
from app import create_app
from models import db, User, Product, Category, Stock, Warehouse, Location, StockMove, StockMoveLine
from inventory_utils import get_default_warehouse, get_default_location

app = create_app({
    'TESTING': True,
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    'WTF_CSRF_ENABLED': False
})

client = app.test_client()

with app.app_context():
    db.create_all()

    print("--- Setting Up Test Environment & Authenticating ---")
    user = User(login_id='warehouse_mgr', email='mgr@stocksense.com')
    user.set_password('mgrpass')
    db.session.add(user)

    warehouse = get_default_warehouse()
    location = get_default_location()

    prod_a = Product(name='Industrial Motor 1HP', sku='MTR-1HP', uom='Units', reorder_point=5.0)
    prod_b = Product(name='Copper Cable 50m', sku='CBL-COP-50', uom='Boxes', reorder_point=10.0)
    db.session.add(prod_a)
    db.session.add(prod_b)
    db.session.commit()

    # Log in
    login_resp = client.post('/auth/login', data={'login_id': 'warehouse_mgr', 'password': 'mgrpass'})
    assert login_resp.status_code == 302, f"Login failed: {login_resp.status_code}"
    print("Warehouse Manager authenticated successfully!")

    print("\n--- 1. Testing Receipt Creation (Draft) ---")
    create_resp = client.post('/operations/receipts/new', data={
        'contact': 'Global Supply Co.',
        'to_location_id': str(location.id),
        'schedule_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'product_id[]': [str(prod_a.id), str(prod_b.id)],
        'quantity[]': ['25', '10']
    }, follow_redirects=False)
    assert create_resp.status_code == 302, f"Expected 302 redirect, got {create_resp.status_code}"

    # Verify move was saved as Draft with WH<id>/IN/<seq> reference format
    move1 = StockMove.query.filter_by(contact='Global Supply Co.').first()
    assert move1 is not None, "StockMove should exist"
    assert move1.type == 'IN'
    assert move1.status == 'Draft'
    assert move1.reference.startswith(f"WH{warehouse.id}/IN/"), f"Reference {move1.reference} should follow WH<id>/IN/<seq>"
    assert len(move1.lines) == 2, "Move should have 2 lines"
    assert move1.responsible_user_id == user.id, "Responsible user should be session user"

    # Verify stock has NOT changed in Draft
    stock_a = Stock.query.filter_by(product_id=prod_a.id, location_id=location.id).first()
    assert stock_a is None or stock_a.on_hand == 0.0, "Stock should remain unchanged during Draft"
    print(f"Receipt created as Draft with reference {move1.reference}!")

    print("\n--- 2. Testing First Validation (Draft -> Ready) ---")
    val1_resp = client.post(f'/operations/receipts/{move1.id}/validate', follow_redirects=False)
    assert val1_resp.status_code == 302

    db.session.refresh(move1)
    assert move1.status == 'Ready', f"Expected status 'Ready', got {move1.status}"

    # Verify stock has NOT changed yet in Ready state
    stock_a_ready = Stock.query.filter_by(product_id=prod_a.id, location_id=location.id).first()
    assert stock_a_ready is None or stock_a_ready.on_hand == 0.0, "Stock should not change in Ready state"
    print("Transitioned Draft -> Ready, verified stock still untouched!")

    print("\n--- 3. Testing Second Validation (Ready -> Done) with Atomic Stock Delta ---")
    val2_resp = client.post(f'/operations/receipts/{move1.id}/validate', follow_redirects=False)
    assert val2_resp.status_code == 302

    db.session.refresh(move1)
    assert move1.status == 'Done', f"Expected status 'Done', got {move1.status}"

    # Verify stock delta applied atomically
    stock_a_done = Stock.query.filter_by(product_id=prod_a.id, location_id=location.id).first()
    stock_b_done = Stock.query.filter_by(product_id=prod_b.id, location_id=location.id).first()
    assert stock_a_done is not None and stock_a_done.on_hand == 25.0, f"Expected 25.0 on hand, got {stock_a_done.on_hand if stock_a_done else None}"
    assert stock_b_done is not None and stock_b_done.on_hand == 10.0, f"Expected 10.0 on hand, got {stock_b_done.on_hand if stock_b_done else None}"
    assert prod_a.total_on_hand == 25.0
    assert prod_b.total_on_hand == 10.0
    print("Transitioned Ready -> Done, verified stock delta applied atomically!")

    print("\n--- 4. Testing Detail View & Print Button Behavior ---")
    detail_resp = client.get(f'/operations/receipts/{move1.id}')
    assert detail_resp.status_code == 200
    assert move1.reference.encode() in detail_resp.data
    assert b"Print Slip" in detail_resp.data
    assert b"disabled" not in detail_resp.data.split(b'id="printBtn"')[0][-100:], "Print should be enabled once Done"
    print("Detail page verified: Print button is enabled for Done move!")

    print("\n--- 5. Testing Cancel Never Touches Stock ---")
    # Create a second receipt
    create_resp2 = client.post('/operations/receipts/new', data={
        'contact': 'Second Vendor Corp.',
        'to_location_id': str(location.id),
        'schedule_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'product_id[]': [str(prod_a.id)],
        'quantity[]': ['50']
    }, follow_redirects=False)
    assert create_resp2.status_code == 302

    move2 = StockMove.query.filter_by(contact='Second Vendor Corp.').first()
    assert move2.status == 'Draft'
    assert move2.reference.startswith(f"WH{warehouse.id}/IN/0002")

    # Cancel it
    cancel_resp = client.post(f'/operations/receipts/{move2.id}/cancel', follow_redirects=False)
    assert cancel_resp.status_code == 302

    db.session.refresh(move2)
    assert move2.status == 'Canceled'

    # Check stock again: prod_a stock must still be exactly 25.0 (unaffected by move2)
    db.session.refresh(stock_a_done)
    assert stock_a_done.on_hand == 25.0, "Stock must NOT change when a move is canceled"
    print("Canceled receipt successfully verified: Stock was completely untouched!")

    print("\n--- 6. Testing Receipts Index Page List ---")
    index_resp = client.get('/operations/receipts/')
    assert index_resp.status_code == 200
    assert move1.reference.encode() in index_resp.data
    assert move2.reference.encode() in index_resp.data
    assert b"Global Supply Co." in index_resp.data
    assert b"Second Vendor Corp." in index_resp.data
    assert b"Done" in index_resp.data
    assert b"Canceled" in index_resp.data
    print("Receipts index list table verified with references, contacts, and statuses!")

print("\n=== ALL RECEIPTS TESTS PASSED PERFECTLY ===")
