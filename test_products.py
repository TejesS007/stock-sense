import sys
from app import create_app
from models import db, User, Product, Category, Stock, Warehouse, Location
from inventory_utils import get_default_location

app = create_app({
    'TESTING': True,
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    'WTF_CSRF_ENABLED': False
})

client = app.test_client()

with app.app_context():
    db.create_all()

    print("--- Setting Up Test User & Authenticating ---")
    user = User(login_id='tester', email='tester@stocksense.com')
    user.set_password('testpass')
    db.session.add(user)
    db.session.commit()

    # Log in
    login_resp = client.post('/auth/login', data={'login_id': 'tester', 'password': 'testpass'})
    assert login_resp.status_code == 302, f"Login failed with status {login_resp.status_code}"
    print("User authenticated successfully!")

    print("\n--- 1. Testing Product Creation without Initial Stock ---")
    cat1 = Category(name='Hardware')
    db.session.add(cat1)
    db.session.commit()

    resp = client.post('/products/create', data={
        'name': 'Steel Bolt M8',
        'sku': 'BOLT-M8',
        'category_id': str(cat1.id),
        'uom': 'Pieces',
        'reorder_point': '50',
        'initial_stock': '0'
    }, follow_redirects=False)
    assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"
    assert resp.headers['Location'].endswith('/products/')

    prod1 = Product.query.filter_by(sku='BOLT-M8').first()
    assert prod1 is not None, "Product should be created in DB"
    assert prod1.name == 'Steel Bolt M8'
    assert prod1.category_id == cat1.id
    assert prod1.uom == 'Pieces'
    assert prod1.reorder_point == 50.0
    assert prod1.total_on_hand == 0.0
    assert prod1.is_low_stock is True, "0 on-hand with 50 reorder point should be low stock"
    print("Product created successfully with correct fields!")

    print("\n--- 2. Testing Product Creation with Inline Category ---")
    resp_inline = client.post('/products/create', data={
        'name': 'Polymer Washer',
        'sku': 'WSH-POLY-10',
        'category_id': '',
        'new_category': 'Fasteners',
        'uom': 'Units',
        'reorder_point': '10',
        'initial_stock': '0'
    }, follow_redirects=False)
    assert resp_inline.status_code == 302

    new_cat = Category.query.filter_by(name='Fasteners').first()
    assert new_cat is not None, "New category should be created inline"
    prod2 = Product.query.filter_by(sku='WSH-POLY-10').first()
    assert prod2.category_id == new_cat.id
    print("Inline category creation works as expected!")

    print("\n--- 3. Testing SKU Collision Validation ---")
    resp_collision = client.post('/products/create', data={
        'name': 'Duplicate Bolt',
        'sku': 'bolt-m8',  # case-insensitive check
        'category_id': str(cat1.id),
        'uom': 'Pieces',
        'reorder_point': '10',
        'initial_stock': '0'
    })
    assert resp_collision.status_code == 400
    assert b"already in use" in resp_collision.data, "Should display inline SKU collision error"
    print("SKU uniqueness collision correctly caught and returned HTTP 400!")

    print("\n--- 4. Testing Product Creation with Initial Stock ---")
    default_loc = get_default_location()
    resp_stock = client.post('/products/create', data={
        'name': 'Brass Fitting 1/2',
        'sku': 'FIT-BRASS-05',
        'category_id': str(cat1.id),
        'uom': 'Pieces',
        'reorder_point': '20',
        'initial_stock': '100'
    }, follow_redirects=False)
    assert resp_stock.status_code == 302

    prod3 = Product.query.filter_by(sku='FIT-BRASS-05').first()
    assert prod3 is not None
    stock_row = Stock.query.filter_by(product_id=prod3.id, location_id=default_loc.id).first()
    assert stock_row is not None, "Stock row must be created at default location"
    assert stock_row.on_hand == 100.0
    assert prod3.total_on_hand == 100.0
    assert prod3.is_low_stock is False, "100 on-hand > 20 reorder point should not be low stock"
    print("Initial stock row successfully created at default location!")

    print("\n--- 5. Testing Product Index Page Table & Low Stock Indicator ---")
    index_resp = client.get('/products/')
    assert index_resp.status_code == 200
    assert b"Steel Bolt M8" in index_resp.data
    assert b"BOLT-M8" in index_resp.data
    assert b"FIT-BRASS-05" in index_resp.data
    assert b"Low Stock" in index_resp.data or b"Out of Stock" in index_resp.data
    print("Product catalog table renders correctly with low-stock badges!")

    print("\n--- 6. Testing Product Edit ---")
    edit_resp = client.post(f'/products/{prod1.id}/edit', data={
        'name': 'Steel Bolt M8 Premium',
        'sku': 'BOLT-M8-PREM',
        'category_id': str(cat1.id),
        'new_category': '',
        'uom': 'Pieces',
        'reorder_point': '25'
    }, follow_redirects=False)
    assert edit_resp.status_code == 302

    updated_prod = db.session.get(Product, prod1.id)
    assert updated_prod.name == 'Steel Bolt M8 Premium'
    assert updated_prod.sku == 'BOLT-M8-PREM'
    assert updated_prod.reorder_point == 25.0

    # Collision test on edit with another product's SKU
    edit_coll = client.post(f'/products/{prod1.id}/edit', data={
        'name': 'Trying collision',
        'sku': 'FIT-BRASS-05',
        'category_id': str(cat1.id),
        'uom': 'Pieces',
        'reorder_point': '25'
    })
    assert edit_coll.status_code == 400
    assert b"already in use" in edit_coll.data
    print("Product edit and collision validation work perfectly!")

print("\n=== ALL PRODUCT TESTS PASSED PERFECTLY ===")
