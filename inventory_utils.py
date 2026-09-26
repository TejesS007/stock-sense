from models import db, Warehouse, Location, StockMove


def get_default_location():
    """Ensure at least one warehouse and stock location exists and return the default location."""
    location = Location.query.first()
    if not location:
        warehouse = Warehouse.query.first()
        if not warehouse:
            warehouse = Warehouse(
                name="Main Warehouse",
                short_code="WH1",
                address="Central Warehouse Facility"
            )
            db.session.add(warehouse)
            db.session.flush()

        location = Location(
            name="Stock",
            short_code="STOCK",
            warehouse_id=warehouse.id
        )
        db.session.add(location)
        db.session.commit()

    return location


def get_default_warehouse():
    """Return the default warehouse, creating one if needed."""
    warehouse = Warehouse.query.first()
    if not warehouse:
        warehouse = Warehouse(
            name="Main Warehouse",
            short_code="WH1",
            address="Central Warehouse Facility"
        )
        db.session.add(warehouse)
        db.session.flush()

        location = Location(
            name="Stock",
            short_code="STOCK",
            warehouse_id=warehouse.id
        )
        db.session.add(location)
        db.session.commit()

    return warehouse


def generate_move_reference(warehouse_id, move_type):
    """
    Generate auto-incrementing move reference in the format:
    WH<warehouse_id>/<IN|OUT|INT|ADJ>/<auto-increment, per type>
    e.g. WH1/IN/0001
    """
    # Map type to abbreviation
    type_abbr_map = {
        'IN': 'IN',
        'OUT': 'OUT',
        'INTERNAL': 'INT',
        'INT': 'INT',
        'ADJUSTMENT': 'ADJ',
        'ADJ': 'ADJ'
    }
    abbr = type_abbr_map.get(move_type, move_type)
    prefix = f"WH{warehouse_id}/{abbr}/"

    count = StockMove.query.filter(StockMove.reference.like(f"{prefix}%")).count()
    seq = count + 1

    reference = f"{prefix}{seq:04d}"
    while StockMove.query.filter_by(reference=reference).first():
        seq += 1
        reference = f"{prefix}{seq:04d}"

    return reference
