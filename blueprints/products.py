from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Product, Category, Stock
from inventory_utils import get_default_location
from .auth import login_required

products_bp = Blueprint('products', __name__, url_prefix='/products')


@products_bp.route('/')
@login_required
def index():
    products = Product.query.order_by(Product.name).all()
    return render_template('products/index.html', products=products)


@products_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    categories = Category.query.order_by(Category.name).all()
    errors = {}
    form_data = {
        'name': '',
        'sku': '',
        'category_id': '',
        'new_category': '',
        'uom': 'Units',
        'reorder_point': '0',
        'initial_stock': '0'
    }

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        sku = request.form.get('sku', '').strip().upper()
        category_id_val = request.form.get('category_id', '').strip()
        new_category = request.form.get('new_category', '').strip()
        uom = request.form.get('uom', '').strip() or 'Units'
        reorder_point_str = request.form.get('reorder_point', '0').strip()
        initial_stock_str = request.form.get('initial_stock', '0').strip()

        form_data.update({
            'name': name,
            'sku': sku,
            'category_id': category_id_val,
            'new_category': new_category,
            'uom': uom,
            'reorder_point': reorder_point_str,
            'initial_stock': initial_stock_str
        })

        # Validation
        if not name:
            errors['name'] = 'Product Name is required.'

        if not sku:
            errors['sku'] = 'SKU / Code is required.'
        else:
            existing = Product.query.filter_by(sku=sku).first()
            if existing:
                errors['sku'] = f'SKU "{sku}" is already in use by product "{existing.name}".'

        try:
            reorder_point = float(reorder_point_str)
            if reorder_point < 0:
                errors['reorder_point'] = 'Reorder point cannot be negative.'
        except (ValueError, TypeError):
            errors['reorder_point'] = 'Reorder point must be a valid number.'
            reorder_point = 0.0

        try:
            initial_stock = float(initial_stock_str or 0)
            if initial_stock < 0:
                errors['initial_stock'] = 'Initial stock cannot be negative.'
        except (ValueError, TypeError):
            errors['initial_stock'] = 'Initial stock must be a valid number.'
            initial_stock = 0.0

        # Category resolution
        category_id = None
        if new_category:
            existing_cat = Category.query.filter(
                db.func.lower(Category.name) == new_category.lower()
            ).first()
            if existing_cat:
                category_id = existing_cat.id
            else:
                new_cat_obj = Category(name=new_category)
                db.session.add(new_cat_obj)
                db.session.flush()
                category_id = new_cat_obj.id
        elif category_id_val and category_id_val.isdigit():
            category_id = int(category_id_val)

        if not errors:
            product = Product(
                name=name,
                sku=sku,
                category_id=category_id,
                uom=uom,
                reorder_point=reorder_point
            )
            db.session.add(product)
            db.session.flush()

            # Create matching Stock row if initial stock is provided
            if initial_stock > 0:
                default_loc = get_default_location()
                stock_entry = Stock(
                    product_id=product.id,
                    location_id=default_loc.id,
                    on_hand=initial_stock,
                    reserved=0.0
                )
                db.session.add(stock_entry)

            db.session.commit()
            flash(f'Product "{product.name}" (SKU: {product.sku}) created successfully.', 'success')
            return redirect(url_for('products.index'))

        return render_template(
            'products/create.html',
            categories=categories,
            form_data=form_data,
            errors=errors
        ), 400

    return render_template(
        'products/create.html',
        categories=categories,
        form_data=form_data,
        errors=errors
    )


@products_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    product = db.session.get(Product, id)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('products.index'))

    categories = Category.query.order_by(Category.name).all()
    errors = {}

    form_data = {
        'name': product.name,
        'sku': product.sku,
        'category_id': str(product.category_id or ''),
        'new_category': '',
        'uom': product.uom,
        'reorder_point': str(product.reorder_point)
    }

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        sku = request.form.get('sku', '').strip().upper()
        category_id_val = request.form.get('category_id', '').strip()
        new_category = request.form.get('new_category', '').strip()
        uom = request.form.get('uom', '').strip() or 'Units'
        reorder_point_str = request.form.get('reorder_point', '0').strip()

        form_data.update({
            'name': name,
            'sku': sku,
            'category_id': category_id_val,
            'new_category': new_category,
            'uom': uom,
            'reorder_point': reorder_point_str
        })

        if not name:
            errors['name'] = 'Product Name is required.'

        if not sku:
            errors['sku'] = 'SKU / Code is required.'
        else:
            # Check SKU collision excluding this product
            existing = Product.query.filter(Product.sku == sku, Product.id != product.id).first()
            if existing:
                errors['sku'] = f'SKU "{sku}" is already in use by another product.'

        try:
            reorder_point = float(reorder_point_str)
            if reorder_point < 0:
                errors['reorder_point'] = 'Reorder point cannot be negative.'
        except (ValueError, TypeError):
            errors['reorder_point'] = 'Reorder point must be a valid number.'
            reorder_point = product.reorder_point

        category_id = product.category_id
        if new_category:
            existing_cat = Category.query.filter(
                db.func.lower(Category.name) == new_category.lower()
            ).first()
            if existing_cat:
                category_id = existing_cat.id
            else:
                new_cat_obj = Category(name=new_category)
                db.session.add(new_cat_obj)
                db.session.flush()
                category_id = new_cat_obj.id
        elif category_id_val and category_id_val.isdigit():
            category_id = int(category_id_val)
        elif category_id_val == '':
            category_id = None

        if not errors:
            product.name = name
            product.sku = sku
            product.category_id = category_id
            product.uom = uom
            product.reorder_point = reorder_point

            db.session.commit()
            flash(f'Product "{product.name}" updated successfully.', 'success')
            return redirect(url_for('products.index'))

        return render_template(
            'products/edit.html',
            product=product,
            categories=categories,
            form_data=form_data,
            errors=errors
        ), 400

    return render_template(
        'products/edit.html',
        product=product,
        categories=categories,
        form_data=form_data,
        errors=errors
    )
