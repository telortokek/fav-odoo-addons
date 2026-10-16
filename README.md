# FAV Odoo addons

Custom addons for [FAV](https://github.com/telortokek/fav-odoo-addons), a rental business that also sells food and beverages on site. Odoo Community is the system of record for POS, the F&B menu, inventory, sales, and invoicing. The booking website stays the customer-facing front and pushes confirmed bookings into Odoo.

Odoo itself is not in this repository. Local development runs the official `odoo` image. The series is **20.0 Community**. Change it in `.env` (`ODOO_VERSION`) and keep the module version prefix (`20.0.x.y.z` in `fav_booking/__manifest__.py`) on the same series.

## Architecture

```
booking website                    Odoo
---------------                    ----
customer picks a slot
        |
        |  POST /fav/api/booking/upsert
        |  Authorization: Bearer <API key>
        v
                                 fav.booking  (draft → confirmed)
                                        |
                                        |  guest arrives
                                        v
                                 cashier opens a POS session,
                                 adds F&B, links pos.order
                                 on the booking
                                        |
                                        v
                                 sale.order / invoice when the
                                 rental charge is billed in Sales
```

Loyverse remains in use until products, customers, and stock have been loaded into Odoo. The Google Sheet used for manual booking checks is replaced by `fav.booking` once the website calls this API.

`external_ref` is the website's idempotency key. Repeating the same reference updates a draft or confirmed booking and returns the same record. It does not create a second booking. After check-in, schedule and amount fields stay as they are. A retry that still says `confirmed` does not rewind a booking that staff have already checked in.

Point of Sale orders are created in an open POS session, where the cashier adds food and beverages. The booking form stores the link. A **Create Sales Order** button on a confirmed booking opens a draft sales order for the rental product when the charge should go through Sales and invoicing.

## Run locally

Docker and Docker Compose are required.

```bash
cp .env.example .env
docker compose up -d
```

Open <http://localhost:8069>. The database manager password in `config/odoo.conf` is `admin` for local development. Change `admin_passwd` before this port is reachable from anywhere else.

Create a database (demo data is optional). Then install **FAV Booking** from Apps. Activate developer mode and use **Update Apps List** if the module is not listed yet. The app depends on Sales and Point of Sale; installing it installs those too.

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
    "product_code": "COURT-HOUR",
    "date_start": "2026-10-20 02:00:00",
    "date_end": "2026-10-20 04:00:00",
    "state": "confirmed",
    "amount_untaxed": 150000,
    "amount_tax": 0,
    "amount_total": 150000,
    "note": "Online"
  }'
```

`product_id` may be sent instead of `product_code`, and `partner_id` instead of `partner`. The resource is a normal product (`product.product`) with an internal reference. Create the rentable units (courts, rooms, slots) as products before the website calls the API.

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

## Tests

```bash
docker compose run --rm odoo -d fav_ci -i fav_booking --without-demo=all --stop-after-init --test-enable --test-tags /fav_booking
```

GitHub Actions runs flake8 and this install.

## Odoo 20 notes that shaped the module

Checked against the 20.0 sources:

- List views use `<list>`, and window actions use `view_mode` `list,form`. `<tree>` is the old name.
- Access rights are `ir.access` records in `security/ir.access.csv` (`model`, group external id, operation such as `cru` / `crud`, optional domain). `ir.model.access` and the old `perm_read` columns are gone. An empty group is a restriction; the multi-company line uses that.
- Groups hang off `res.groups.privilege` (`privilege_id`), not `category_id` on `res.groups`. Users are `user_ids`.
- SQL constraints are `models.Constraint` attributes. `_sql_constraints` is gone.
- HTTP JSON routes are `type='jsonrpc'` (the old `type='json'`) or `type='json2'` for a plain JSON body. This module's endpoint is `json2`.
- API keys are bearer tokens. Scope `rpc` is what `auth='bearer'` checks. Keys expire; plan rotation.

## Next steps

- **Loyverse migration.** Export items, customers, and stock counts. Load items as products (sellable, and storable when they are goods), customers as partners, and on-hand quantities as inventory adjustments. Map Loyverse categories onto POS categories so the cashier's menu matches the current till.
- **Booking website.** Point the existing site at `upsert_from_website` after a slot is confirmed. Keep using `external_ref` as the website booking id. Payment capture on the website can stay as it is until the gateway below writes payments back onto the sales order or invoice.
- **Payments.** Add a provider such as Midtrans or Xendit for booking prepayment and for invoices. That is a separate module (`payment` provider) and is not part of this baseline.
- **Deployment.** Put Postgres and Odoo on a private network, set `list_db = False`, set a real `admin_passwd`, set `proxy_mode = True` behind HTTPS, and set `dbfilter` (or `PGDATABASE`) to the production database. Raise `workers` once the traffic is known. Do not publish the database manager.
