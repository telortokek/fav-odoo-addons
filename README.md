# FAV Odoo addons

Custom addons for [FAV](https://github.com/telortokek/fav-odoo-addons), a rental business that also sells food and beverages on site. Odoo Community is the system of record for POS, the F&B menu, inventory, sales, and invoicing. The booking website stays the customer-facing front and pushes confirmed bookings into Odoo.

Odoo itself is not in this repository. Local development runs the official `odoo` image. The series is **20.0 Community**. Change it in `.env` (`ODOO_VERSION`) and keep the module version prefix (`20.0.x.y.z` in each `__manifest__.py`) on the same series.

## Architecture

```
booking website                         Odoo
----------------                         ----
customer or walk-in books in the app
        |
        |  POST /fav/api/booking/upsert
        |  Authorization: Bearer <API key>
        v
                                 fav.booking  (draft → confirmed)
                                 matched to fav.room
                                        |
                                        |  guest arrives, staff press Check In
                                        v
                                 draft pos.order on that room's table
                                 (room hours, minus what was paid on the website)
                                 cashier adds F&B on the same bill
```

Loyverse remains in use until products, customers, and stock have been loaded into Odoo. The Google Sheet used for manual booking checks is replaced by `fav.booking` once the website calls this API.

The website is the only place a booking is created, including walk-ins. Staff can open the calendar, confirm, and check a guest in. The Booking list, form, calendar, and kanban do not offer **New**, and the access rights have no create permission. `upsert_from_website` is the creator: it checks that the caller may write bookings, then creates the record with `sudo()`.

`external_ref` is the website's idempotency key. Repeating the same reference updates a draft or confirmed booking and returns the same record. It does not create a second booking. After check-in, schedule and amount fields stay as they are. A retry that still says `confirmed` does not rewind a booking that staff have already checked in.

Opening a POS session creates a draft bill for every confirmed booking on that floor whose start falls on the current local day (the user timezone, or Asia/Jakarta). A booking confirmed through the API while that session is already open gets its bill immediately. Future days stay on the schedule until the register opens that day. The booking becomes **Checked In** when the bill is created. There is no Check In button. If the table already has a draft order, a second bill is still opened and the booking chatter says so. A failure is written on the booking and does not stop the session from opening.

## Run locally

Docker and Docker Compose are required.

```bash
cp .env.example .env
docker compose up -d
```

Open <http://localhost:8069>. The database manager password in `config/odoo.conf` is `admin` for local development. Change `admin_passwd` before this port is reachable from anywhere else.

Create a database (demo data is optional). Then install **FAV Booking** and **FAV POS Outlet Analytic** from Apps. Activate developer mode and use **Update Apps List** if a module is not listed yet. Booking depends on Sales and on **FAV POS Room Names**, which installs Restaurant and Point of Sale. Outlet analytic depends on Point of Sale.

Upgrade an existing database with:

```bash
docker compose run --rm odoo -d fav -u fav_booking --stop-after-init
docker compose up -d
```

To initialize a database from the command line instead of the manager UI:

```bash
docker compose run --rm odoo -d fav -i fav_booking --without-demo=all --stop-after-init
docker compose up -d
```

The first install builds the chart of accounts, POS, and sales and takes several minutes. PostgreSQL data and the Odoo filestore are kept in the `fav-db-data` and `fav-odoo-data` volumes.

Database credentials live in `.env` (`POSTGRES_USER`, `POSTGRES_PASSWORD`). Compose passes them to Postgres and to Odoo as `PGUSER` / `PGPASSWORD`. `.env` is gitignored. Do not commit real passwords.

`config/odoo.conf` does not set `db_host` or `db_password`. Odoo 20 reads `PGHOST`, `PGPORT`, `PGUSER`, and `PGPASSWORD`.

## Booking API

Create an internal user for the website (Settings → Users), for example `fav_website`. Give that user **FAV / Booking: Administrator**. That group can create and update bookings and create contacts. A Booking **User** can work bookings in the UI but cannot create new contacts, so the website user should be an administrator (or otherwise belong to **Contact Creation / partner manager**).

On that user: Preferences → Account Security → New API Key. Scope is **RPC**. Odoo 20 will not issue a key longer than about three months, so the website must rotate it. Store the key outside this repository.

Send datetimes in UTC, format `YYYY-MM-DD HH:MM:SS`.

```bash
curl -sS -X POST http://localhost:8069/fav/api/booking/upsert \
  -H "Authorization: Bearer $FAV_API_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Odoo-Database: fav" \
  -d '{
    "external_ref": "WEB-1001",
    "partner": {"name": "Ayu", "email": "ayu@example.com", "phone": "081234"},
    "room_code": "VIP-PLUS-1",
    "product_code": "COURT-HOUR",
    "date_start": "2026-10-20 02:00:00",
    "date_end": "2026-10-20 04:00:00",
    "state": "confirmed",
    "amount_untaxed": 300000,
    "amount_tax": 0,
    "amount_total": 300000,
    "amount_paid": 300000,
    "note": "Online"
  }'
```

`product_id` may be sent instead of `product_code`, and `partner_id` instead of `partner`. `room_code` (or `room_id`) selects a room configured under **FAV → Configuration → Rooms**. That room's product becomes the booking product. A `product_code` that matches a room code does the same, so older callers that sent the room code as the product reference still resolve. When no room matches, the product is used on its own and check-in cannot open a table.

## Rooms, calendar, and check-in

**FAV → Configuration → Rooms** links three things:

- a **room code** the website sends
- a **POS table** (`restaurant.table`, whose floor-plan name comes from `fav_pos_room`)
- a **product** that is available in the Point of Sale and priced per hour

Do not put the hourly price on the room. Change it on the product.

**FAV → Bookings** opens the day schedule. Time runs down the page in the outlet's slot size (30 minutes by default) from the outlet's opening hour to its closing hour. The default window is 09:00 to 02:00 the next day; set **Schedule Opens**, **Schedule Closes**, and **Schedule Slot** on the floor. Hours past 24 are the next morning, so 26 is 02:00. Rooms are columns, ordered and labelled by room type. Each booking is a block with the customer, time, status colour, and website payment. The view is read-only. Click a block to open the booking; **Bill** opens the POS order when one exists. The outlet selector shows one floor at a time (for example FAV Setiabudi or FAV Rental Tenun) and the browser remembers the last choice. **All Bookings** keeps the calendar, list, and kanban, with an Outlet filter and group-by. Community has no Gantt view. Two bookings for the same room cannot overlap unless one is cancelled. A booking that ends when the next one starts is allowed.

The bill is a draft `pos.order` on the room's table, with the customer. The room line quantity is the number of hours between start and end. The unit price is the POS pricelist price (the product list price when the register has no pricelist). Staff cannot edit the date, room, or payment on the booking form. A draft booking can still be confirmed, which opens today's bill if the register is already open.

Bookings are usually paid in full on the website. Send `amount_paid` (the form field is **Payment**). `amount_down_payment` is still accepted and stored under that technical name; if both are sent, `amount_paid` wins. When the amount is greater than zero, check-in adds a second line on the same product with a negative unit price, no taxes, `price_type=manual`, the name **Website payment**, and the note **Paid on website for** the booking number. The credit is the exact amount collected, so a payment equal to the room charge on the bill leaves a zero total. It is not a `pos.payment`, so the register does not expect that money in the drawer. A negative payment, or one larger than the room charge, is rejected.

Reload the Point of Sale after check-in. Draft orders for that register are part of the data the POS loads (`pos.order` domain `state = draft` and this config). Check-in also sends the register a synchronisation message so a session that is already open can pick the bill up without a full reload.

## Manual check

1. Upgrade with `-u fav_booking` (command above) and open a restaurant POS session.
2. Create a room: code `VIP-PLUS-1`, the POS table for that room, and an hourly product available in POS.
3. Send the upsert sample with `room_code` `VIP-PLUS-1`. The booking is confirmed and has no **New** button in the UI.
4. Open the register. Today's booking is already a draft bill on its table. A booking sent for today while the session is open appears as well. A booking for tomorrow does not, until that day's session opens.
5. **FAV → Bookings** shows the day schedule for the selected outlet. Click a block for the booking, and **Bill** for the POS order.

The same body works on Odoo's JSON-2 API, which is the supported external RPC in Odoo 20:

```bash
curl -sS -X POST http://localhost:8069/json/2/fav.booking/upsert_from_website \
  -H "Authorization: Bearer $FAV_API_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Odoo-Database: fav" \
  -d @payload.json
```

`/jsonrpc` and `/xmlrpc` still exist but are deprecated and should not be used for new work. The module route is `type='json2'` with `auth='bearer'` and `bearer_scope='rpc'`, so the key has the caller's groups and record rules. The controller does not use `sudo`.

A successful body looks like:

```json
{
  "id": 1,
  "name": "BK00001",
  "state": "confirmed",
  "external_ref": "WEB-1001",
  "partner_id": 42,
  "product_id": 7,
  "created": true
}
```

`created` is `false` when `external_ref` already existed. Status values are `draft`, `confirmed`, `checked_in`, `done`, and `cancelled`.

## Room names on the POS floor

FAV uses each restaurant table as a rental room. Odoo 20 only stores an integer `table_number`, so the floor plan and tickets would show `1`, `2`, and so on. `fav_pos_room` adds **Room Name** on `restaurant.table`.

Set it under **Point of Sale → Configuration → Floor Plans**. Open the floor and edit the **Room Name** column on the table list (the table form has the same field). Leave it empty to keep showing the table number.

The name is what the POS shows on:

- floor-plan tiles, including the floor editor
- the order header (the badge next to the register)
- the order list badge, which can also be searched by room name
- the customer receipt and the kitchen / preparation ticket

Combined tables join each room name with ` & `. A name that is only spaces is treated as empty.

After changing a name, **reload the Point of Sale** (close it and open it again, or reload the page). The POS reads `room_name` when it loads its data, so a session that is already open keeps the previous labels until that reload.

On install, blank tables on a floor named exactly `FAV Setiabudi` are filled from the current layout, matched by table number, not by database id:

| Number | Room name |
| --- | --- |
| 1–5 | VIP PLUS 1–5 |
| 6–7 | VVIP 1–2 |
| 8–9 | DELUXE 1–2 |
| 10 | SUITE 1 |

A table that already has a room name is left as it is. Tables created later on that floor get the same default when Room Name is left empty. Other floors are ignored. The fill does not run again on module upgrade, so clearing a name afterwards keeps the table number on screen. If the floor did not exist yet at install time, set the names on the floor form, or create the tables on that floor and leave Room Name empty so the default is applied.

## Outlet analytic on the POS

Odoo 20 Community does not put an analytic account on the register. **FAV POS Outlet Analytic** adds **Outlet analytic account** on `pos.config`.

Create the accounts once, under **Accounting → Configuration → Analytic Accounting** (developer mode is not required for these menus once Accounting is installed):

1. Create an analytic plan named `Outlet`.
2. On that plan, create one analytic account per outlet. FAV uses `FAV Setiabudi` with code `SBD`, and `FAV Tenun` with code `TNN`. The module does not create these records.
3. Open **Point of Sale → Configuration → Settings**, select the register, and under **Accounting** set **Outlet analytic account**. The same field is on the register form, Configuration page.

When that register closes a session, the closing journal entry gets `analytic_distribution` `{account: 100}` on every income line and on discount and other profit-and-loss lines (expense, depreciation, and cost of goods). Receivable, bank, cash, and tax lines are left untagged. An invoice created from a POS order gets the same distribution on its product lines.

A room shows **Outlet analytic account** when its floor is linked to a register that has one. That value is computed. It is not a second place to edit the account.

## Tests

```bash
docker compose run --rm odoo -d fav_ci -i fav_booking,fav_pos_room,fav_pos_analytic --without-demo=all --stop-after-init --test-enable --test-tags /fav_booking,/fav_pos_room,/fav_pos_analytic
```

GitHub Actions runs flake8 and this install.

## Technical notes

Checked against the Odoo 20.0 sources:

- List views use `<list>`, and window actions use `view_mode`. `<tree>` is the old name. Bookings default to `calendar,list,kanban,form`.
- Access rights are `ir.access` records in `security/ir.access.csv` (`model`, group external id, operation such as `ru` / `rud`, optional domain). `ir.model.access` and the old `perm_read` columns are gone. An empty group is a restriction; the multi-company lines use that. Booking users and administrators have no `c` (create) on `fav.booking`.
- Groups hang off `res.groups.privilege` (`privilege_id`), not `category_id` on `res.groups`. Users are `user_ids` / `group_ids`.
- SQL constraints are `models.Constraint` attributes. `_sql_constraints` is gone. Room overlap is a Python constraint (cancelled bookings excluded) plus `SELECT … FOR UPDATE` on the room row. Community does not ship `web_gantt`.
- HTTP JSON routes are `type='jsonrpc'` (the old `type='json'`) or `type='json2'` for a plain JSON body. This module's endpoint is `json2`.
- API keys are bearer tokens. Scope `rpc` is what `auth='bearer'` checks. Keys expire; plan rotation.
- A draft `pos.order` with `table_id` set is the open bill. The POS loads it when `state` is `draft` and `config_id` is the register (`pos.order._load_pos_data_domain`). Creating a bill also calls `pos.config._notify_synchronisation`. Session open is `pos.session.create` / `write` when `state` becomes `opened` (`_set_opening_control_data` writes that state). The local day uses `res.users.tz`, or `Asia/Jakarta` when the user has none. `date_start` in that zone selects the day. An API change updates the draft bill only when every line is marked `fav_line_role` `room` or `payment`. Extra lines are left in place and noted on the booking. Cancelling or moving the booking off that day cancels an untouched bill. The day schedule is the client action `fav_booking.schedule`.
- Website money is stored on `fav.booking.amount_down_payment` (form label **Payment**). The API accepts `amount_paid`, which wins when both are sent, and still accepts `amount_down_payment`. Check-in posts a negative untaxed `pos.order.line` named **Website payment** (`price_type=manual`), capped at the room charge on the bill. It is not a `pos.payment`: a payment record would be counted in the session (cash, bank, or customer account) even though the website took the money outside the register. Putting the room product's taxes on that line would also turn a 100,000 collection into a larger credit.
- Outlet analytic is `pos.config.analytic_account_id`. `fav_pos_analytic` writes it after `pos.session._create_session_account_move` and `pos.order._generate_pos_order_invoice` return. Both methods post the move before returning, so cost-of-goods lines created during posting are already on the move. The distribution is a JSON object whose key is the analytic account id as a string and whose value is `100`. Lines are included when `account_id.account_type` is `income`, `income_other`, `expense`, `expense_depreciation`, or `expense_direct_cost`, and `display_type` is not `payment_term`, `tax`, `line_section`, `line_subsection`, or `line_note`. Writing the field on a posted line runs the analytic inverse, which recreates `account.analytic.line`. `fav.room.outlet_analytic_account_id` is a non-stored compute. `fav_booking` does not depend on `fav_pos_analytic`; the field stays empty until that module is installed and a register on the room's floor has an account.

## Next steps

- **Loyverse migration.** Export items, customers, and stock counts. Load items as products (sellable, and storable when they are goods), customers as partners, and on-hand quantities as inventory adjustments. Map Loyverse categories onto POS categories so the cashier's menu matches the current till.
- **Booking website.** Point the existing site at `upsert_from_website` after a slot is confirmed. Keep using `external_ref` as the website booking id. Payment capture on the website can stay as it is until the gateway below writes payments back onto the sales order or invoice.
- **Payments.** Add a provider such as Midtrans or Xendit for booking prepayment and for invoices. That is a separate module (`payment` provider) and is not part of this baseline.
- **Deployment.** Put Postgres and Odoo on a private network, set `list_db = False`, set a real `admin_passwd`, set `proxy_mode = True` behind HTTPS, and set `dbfilter` (or `PGDATABASE`) to the production database. Raise `workers` once the traffic is known. Do not publish the database manager.
