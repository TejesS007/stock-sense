from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Warehouse, Location
from .auth import login_required

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/warehouse', methods=['GET', 'POST'])
@login_required
def warehouse():
    errors = {}
    form_data = {'name': '', 'short_code': '', 'address': ''}

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        short_code = request.form.get('short_code', '').strip().upper()
        address = request.form.get('address', '').strip()
        form_data.update({'name': name, 'short_code': short_code, 'address': address})

        if not name:
            errors['name'] = 'Warehouse name is required.'
        if not short_code:
            errors['short_code'] = 'Short code is required.'
        elif Warehouse.query.filter_by(short_code=short_code).first():
            errors['short_code'] = f'Short code "{short_code}" is already in use.'

        if not errors:
            wh = Warehouse(name=name, short_code=short_code, address=address or None)
            db.session.add(wh)
            db.session.commit()
            flash(f'Warehouse "{wh.name}" created.', 'success')
            return redirect(url_for('settings.warehouse'))

        warehouses = Warehouse.query.order_by(Warehouse.name).all()
        return render_template('settings/warehouse.html', warehouses=warehouses,
                                form_data=form_data, errors=errors), 400

    warehouses = Warehouse.query.order_by(Warehouse.name).all()
    return render_template('settings/warehouse.html', warehouses=warehouses, form_data=form_data, errors=errors)


@settings_bp.route('/location', methods=['GET', 'POST'])
@login_required
def location():
    errors = {}
    form_data = {'name': '', 'short_code': '', 'warehouse_id': ''}
    warehouses = Warehouse.query.order_by(Warehouse.name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        short_code = request.form.get('short_code', '').strip().upper()
        warehouse_id_str = request.form.get('warehouse_id', '').strip()
        form_data.update({'name': name, 'short_code': short_code, 'warehouse_id': warehouse_id_str})

        if not name:
            errors['name'] = 'Location name is required.'
        if not short_code:
            errors['short_code'] = 'Short code is required.'
        if not warehouse_id_str or not warehouse_id_str.isdigit():
            errors['warehouse_id'] = 'A warehouse must be selected.'
        elif not db.session.get(Warehouse, int(warehouse_id_str)):
            errors['warehouse_id'] = 'Selected warehouse does not exist.'

        if not errors:
            loc = Location(name=name, short_code=short_code, warehouse_id=int(warehouse_id_str))
            db.session.add(loc)
            db.session.commit()
            flash(f'Location "{loc.name}" created.', 'success')
            return redirect(url_for('settings.location'))

        locations = Location.query.order_by(Location.warehouse_id, Location.name).all()
        return render_template('settings/location.html', locations=locations, warehouses=warehouses,
                                form_data=form_data, errors=errors), 400

    locations = Location.query.order_by(Location.warehouse_id, Location.name).all()
    return render_template('settings/location.html', locations=locations, warehouses=warehouses,
                            form_data=form_data, errors=errors)
