# StockSense — Inventory Management System

## Entities
- User(id, login_id, email, password_hash)
- Warehouse(id, name, short_code, address)
- Location(id, name, short_code, warehouse_id)
- Category(id, name)
- Product(id, name, sku, category_id, uom, reorder_point)
- Stock(product_id, location_id, on_hand, reserved)
  -- free_to_use = on_hand - reserved
- StockMove(id, reference, type[IN|OUT|INTERNAL|ADJUSTMENT],
  from_location_id, to_location_id, contact, schedule_date,
  status[Draft|Waiting|Ready|Done|Canceled], responsible_user_id, created_at)
- StockMoveLine(move_id, product_id, quantity)

## Reference format
WH<warehouse_id>/<IN|OUT|INT|ADJ>/<auto-increment, per type>

## Status machines
- IN (Receipt): Draft -> Ready -> Done
- OUT (Delivery): Draft -> Waiting -> Ready -> Done
  (Waiting = any line's quantity > free_to_use on that product/location)
- INTERNAL, ADJUSTMENT: Draft -> Done (no intermediate states)
- Validating (Done) applies the stock delta atomically. Cancel never touches stock.
- Print is only enabled once a move is Done.

## Auth
Signup: login_id, email, password. Login: login_id + password.
Forgot password: generate a 6-digit OTP, log it to the server console
(mocked — no real email/SMS), accept it once to allow a password reset.

## Pages
Login, Signup, Dashboard, Products (catalog CRUD), Stock (on-hand table,
inline-editable -> creates an ADJUSTMENT move), Operations > Receipts
(list + detail), Operations > Delivery (list + detail), Operations >
Internal Transfer (list + detail — design this UI, no wireframe exists),
Move History (single ledger of all move types; IN rows green, OUT rows
red, INTERNAL/ADJUSTMENT rows blue), Settings > Warehouse, Settings >
Location.

## Dashboard KPIs
Total products in stock, low-stock/out-of-stock count, pending receipts,
pending deliveries, internal transfers scheduled. Receipt/Delivery cards
show: count to action, "late" count (schedule_date < today), total ops.
