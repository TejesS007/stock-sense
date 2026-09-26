import sys
from app import create_app
from models import db, User, Warehouse, Location, Product

app = create_app({
    'TESTING': True,
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    'WTF_CSRF_ENABLED': False
})

client = app.test_client()

with app.app_context():
    db.create_all()

    print("--- 1. Set Up Authenticated User ---")
    user = User(login_id='testadmin', email='admin@stocksense.com')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    login_resp = client.post('/auth/login', data={'login_id': 'testadmin', 'password': 'password123'})
    assert login_resp.status_code == 302
    print("User authenticated successfully!")

    print("\n--- 2. Create Product (triggering auto-created default warehouse/location) ---")
    prod_resp = client.post('/products/create', data={
        'name': 'Default Product Widget',
        'sku': 'DFLT-WIDGET-001',
        'uom': 'Units',
        'reorder_point': '10',
        'initial_stock': '50'
    }, follow_redirects=False)
    assert prod_resp.status_code == 302

    default_wh = Warehouse.query.first()
    default_loc = Location.query.first()
    assert default_wh is not None, "Default warehouse should be auto-created"
    assert default_loc is not None, "Default location should be auto-created"
    print(f"Default warehouse auto-created: {default_wh.name} ({default_wh.short_code})")
    print(f"Default location auto-created: {default_loc.name} ({default_loc.short_code})")

    print("\n--- 3. Create Second Warehouse & Location via Settings ---")
    wh2_resp = client.post('/settings/warehouse', data={
        'name': 'North Expansion Depot',
        'short_code': 'NED',
        'address': '742 Evergreen Terrace'
    }, follow_redirects=False)
    assert wh2_resp.status_code == 302
    wh2 = Warehouse.query.filter_by(short_code='NED').first()
    assert wh2 is not None
    print(f"Second warehouse created via Settings: {wh2.name} ({wh2.short_code})")

    loc2_resp = client.post('/settings/location', data={
        'name': 'Cold Storage Zone B',
        'short_code': 'COLD-B',
        'warehouse_id': str(wh2.id)
    }, follow_redirects=False)
    assert loc2_resp.status_code == 302
    loc2 = Location.query.filter_by(short_code='COLD-B').first()
    assert loc2 is not None
    print(f"Second location created via Settings: {loc2.name} ({loc2.short_code}) under {wh2.short_code}")

    print("\n--- 4. Verify GET /operations/receipts/new lists the second location ---")
    receipts_resp = client.get('/operations/receipts/new')
    assert receipts_resp.status_code == 200
    html_receipts = receipts_resp.data.decode('utf-8')
    assert 'COLD-B' in html_receipts, "Receipts form must list second location short_code"
    assert 'Cold Storage Zone B' in html_receipts, "Receipts form must list second location name"
    assert 'NED' in html_receipts, "Receipts form must display warehouse short_code"
    print("PASS: /operations/receipts/new successfully lists the second location (NED/Cold Storage Zone B [COLD-B])!")

    print("\n--- 5. Verify GET /operations/delivery/new lists the second location ---")
    delivery_resp = client.get('/operations/delivery/new')
    assert delivery_resp.status_code == 200
    html_delivery = delivery_resp.data.decode('utf-8')
    assert 'COLD-B' in html_delivery, "Delivery form must list second location short_code"
    assert 'Cold Storage Zone B' in html_delivery, "Delivery form must list second location name"
    assert 'NED' in html_delivery, "Delivery form must display warehouse short_code"
    print("PASS: /operations/delivery/new successfully lists the second location (NED/Cold Storage Zone B [COLD-B])!")

    print("\n--- 6. Verify GET /operations/transfers/new lists the second location ---")
    transfers_resp = client.get('/operations/transfers/new')
    assert transfers_resp.status_code == 200
    html_transfers = transfers_resp.data.decode('utf-8')
    assert 'COLD-B' in html_transfers, "Transfers form must list second location short_code"
    assert 'Cold Storage Zone B' in html_transfers, "Transfers form must list second location name"
    assert 'NED' in html_transfers, "Transfers form must display warehouse short_code"
    print("PASS: /operations/transfers/new successfully lists the second location (NED/Cold Storage Zone B [COLD-B])!")

    print("\n=== ALL MULTI-LOCATION DROPDOWN TESTS PASSED SUCCESSFULLY ===")
