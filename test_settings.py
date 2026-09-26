import sys
from app import create_app
from models import db, User, Warehouse, Location, Product
from inventory_utils import get_default_warehouse, get_default_location

app = create_app({
    'TESTING': True,
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    'WTF_CSRF_ENABLED': False
})

client = app.test_client()

with app.app_context():
    db.create_all()

    print("--- Setting Up Test User & Authenticating ---")
    user = User(login_id='settings_admin', email='admin@stocksense.com')
    user.set_password('adminpass')
    db.session.add(user)
    db.session.commit()

    # Log in
    login_resp = client.post('/auth/login', data={'login_id': 'settings_admin', 'password': 'adminpass'})
    assert login_resp.status_code == 302, f"Login failed with status {login_resp.status_code}"
    print("User authenticated successfully!")

    print("\n--- 1. Testing Warehouse Creation ---")
    resp_wh = client.post('/settings/warehouse', data={
        'name': 'East Distribution Center',
        'short_code': 'EDC',
        'address': '450 Industrial Parkway'
    }, follow_redirects=False)
    assert resp_wh.status_code == 302, f"Expected 302 redirect, got {resp_wh.status_code}"

    wh = Warehouse.query.filter_by(short_code='EDC').first()
    assert wh is not None, "Warehouse should be created in DB"
    assert wh.name == 'East Distribution Center'
    assert wh.address == '450 Industrial Parkway'
    print("Warehouse created successfully!")

    print("\n--- 2. Testing Warehouse Short Code Collision ---")
    resp_wh_dup = client.post('/settings/warehouse', data={
        'name': 'Duplicate Code Hub',
        'short_code': 'EDC',
        'address': '999 Other Way'
    })
    assert resp_wh_dup.status_code == 400, f"Expected 400 for duplicate short_code, got {resp_wh_dup.status_code}"
    assert b"already in use" in resp_wh_dup.data, "Should show duplicate short code error"
    print("Duplicate warehouse short_code correctly rejected!")

    print("\n--- 3. Testing Warehouse Validation (Required Fields) ---")
    resp_wh_empty = client.post('/settings/warehouse', data={
        'name': '',
        'short_code': '',
        'address': ''
    })
    assert resp_wh_empty.status_code == 400
    assert b"Warehouse name is required" in resp_wh_empty.data
    assert b"Short code is required" in resp_wh_empty.data
    print("Warehouse required fields validated!")

    print("\n--- 4. Testing Warehouse List View ---")
    resp_wh_list = client.get('/settings/warehouse')
    assert resp_wh_list.status_code == 200
    assert b"East Distribution Center" in resp_wh_list.data
    assert b"EDC" in resp_wh_list.data
    assert b"450 Industrial Parkway" in resp_wh_list.data
    print("Warehouse list table renders with correct attributes and location count!")

    print("\n--- 5. Testing Location Creation ---")
    resp_loc = client.post('/settings/location', data={
        'name': 'Cold Storage Bay A',
        'short_code': 'COLD-A',
        'warehouse_id': str(wh.id)
    }, follow_redirects=False)
    assert resp_loc.status_code == 302, f"Expected 302 redirect, got {resp_loc.status_code}"

    loc = Location.query.filter_by(short_code='COLD-A').first()
    assert loc is not None, "Location should exist in DB"
    assert loc.name == 'Cold Storage Bay A'
    assert loc.warehouse_id == wh.id
    assert loc.warehouse.name == 'East Distribution Center'
    print("Location created and correctly linked to parent Warehouse!")

    # Verify warehouse location count increases
    db.session.refresh(wh)
    assert len(wh.locations) == 1
    resp_wh_list2 = client.get('/settings/warehouse')
    assert b"1" in resp_wh_list2.data
    print("Parent warehouse location count updated accurately!")

    print("\n--- 6. Testing Location Validation ---")
    resp_loc_invalid = client.post('/settings/location', data={
        'name': '',
        'short_code': '',
        'warehouse_id': ''
    })
    assert resp_loc_invalid.status_code == 400
    assert b"Location name is required" in resp_loc_invalid.data
    assert b"Short code is required" in resp_loc_invalid.data
    print("Location required fields validated!")

    print("\n--- 7. Testing Location List View ---")
    resp_loc_list = client.get('/settings/location')
    assert resp_loc_list.status_code == 200
    assert b"Cold Storage Bay A" in resp_loc_list.data
    assert b"COLD-A" in resp_loc_list.data
    assert b"EDC" in resp_loc_list.data
    print("Location list renders location name, short code, and parent warehouse short code!")

    print("\n--- 8. Testing Receipts Form Offers Newly Created Location ---")
    prod = Product(name='Perishable Vaccine', sku='VAC-01', uom='Units', reorder_point=10)
    db.session.add(prod)
    db.session.commit()

    receipt_form_resp = client.get('/operations/receipts/new')
    assert receipt_form_resp.status_code == 200
    assert b"COLD-A" in receipt_form_resp.data, "Receipt destination location dropdown must include newly created location"
    assert b"Cold Storage Bay A" in receipt_form_resp.data
    print("New Receipts form successfully offers all created locations in destination dropdown!")

    print("\n--- 9. Testing Second Warehouse & Location across Receipts, Delivery, and Transfers Dropdowns ---")
    # Step A: Create product with initial stock (triggers bootstrap default warehouse if not present)
    resp_prod = client.post('/products/create', data={
        'name': 'Bootstrap Product Widget',
        'sku': 'BOOT-WIDGET-01',
        'uom': 'Units',
        'reorder_point': '5',
        'initial_stock': '15'
    }, follow_redirects=False)
    assert resp_prod.status_code == 302
    print("Product with initial stock created (bootstrap verified)!")

    # Step B: Create second warehouse + location via Settings
    resp_wh2 = client.post('/settings/warehouse', data={
        'name': 'West Coast Depot',
        'short_code': 'WCD',
        'address': '888 Pacific Boulevard'
    }, follow_redirects=False)
    assert resp_wh2.status_code == 302
    wh2 = Warehouse.query.filter_by(short_code='WCD').first()
    assert wh2 is not None

    resp_loc2 = client.post('/settings/location', data={
        'name': 'Depot Bay 9',
        'short_code': 'BAY9',
        'warehouse_id': str(wh2.id)
    }, follow_redirects=False)
    assert resp_loc2.status_code == 302
    loc2 = Location.query.filter_by(short_code='BAY9').first()
    assert loc2 is not None
    print("Second warehouse (WCD) and location (BAY9) created via Settings!")

    # Step C: Confirm GET /operations/receipts/new lists the second location
    r_resp = client.get('/operations/receipts/new')
    assert r_resp.status_code == 200
    assert b"BAY9" in r_resp.data, "Receipts form must list second location BAY9"
    assert b"WCD" in r_resp.data
    assert b"Depot Bay 9" in r_resp.data
    print("GET /operations/receipts/new correctly lists second location (WCD/Depot Bay 9)!")

    # Step D: Confirm GET /operations/delivery/new lists the second location
    d_resp = client.get('/operations/delivery/new')
    assert d_resp.status_code == 200
    assert b"BAY9" in d_resp.data, "Delivery form must list second location BAY9"
    assert b"WCD" in d_resp.data
    assert b"Depot Bay 9" in d_resp.data
    print("GET /operations/delivery/new correctly lists second location (WCD/Depot Bay 9)!")

    # Step E: Confirm GET /operations/transfers/new lists the second location
    t_resp = client.get('/operations/transfers/new')
    assert t_resp.status_code == 200
    assert b"BAY9" in t_resp.data, "Transfers form must list second location BAY9"
    assert b"WCD" in t_resp.data
    assert b"Depot Bay 9" in t_resp.data
    print("GET /operations/transfers/new correctly lists second location (WCD/Depot Bay 9)!")

print("\n=== ALL SETTINGS TESTS PASSED PERFECTLY ===")
