# Technical notes

## Schedule

The booking board is the client action `fav_booking.schedule` (`fav_booking/static/src/schedule/`). It is read-only. Clicking a booked cell opens the booking form, which already has `edit="0"`.

`fav.booking.get_schedule(day, floor_id, days)` builds the grid.

- Rows are fixed 30-minute slots. The label is the range, for example `10:00-10:30`. The last row of the default window is `01:30-02:00`.
- The opening and closing hours are the system parameters `fav_booking.schedule_start_hour` (default `10`) and `fav_booking.schedule_end_hour` (default `26`). A value above 24 is the next morning, so 26 is 02:00. The floor fields `fav_schedule_start`, `fav_schedule_end`, and `fav_schedule_slot` are not read. The floor form no longer shows them.
- The clock is `res.users.tz`, or `Asia/Jakarta` when the user has no timezone or is still on UTC.
- Columns are `fav.room` records for the selected outlet, ordered by `sequence`, then name. The first column header is `JAM`.
- A booking is one cell with `rowspan` equal to the number of slots it covers (`slot_index` and `slot_span` on each block). The cell shows the customer name in bold and `time_label` (`10:00-12:00`) underneath. `cancelled` is omitted. A stay that starts before opening or ends after closing is clipped to the window. A stay that runs past midnight stays on the board that was already open (the window that contains it), not on the next day's 10:00 grid.
- The legend at the top of the board is the state key: **Confirmed** is blue (`#1d4ed8`), **Checked in** is green (`#15803d`), **Done** is grey (`#64748b`). Text on those blocks is white. Each block is a rounded button inset in the cell.
- Room headers take a pastel from the room type, and the column body uses a lighter tint of the same hue. `VVIP` is violet, other `VIP` names are blue, `Deluxe` is teal, and `Suite` is amber. Rooms in one family use neighboring shades so the columns stay distinct. The type is matched on `room_type` and the room name.
- Rows alternate a light grey wash per hour. The line on the hour is darker and thicker than the half-hour line. Each slot includes `start_minute` counted from midnight of that board's date, so 01:30 the next morning is `1530`.
- `today` and `now_minute` are the schedule clock. When that instant falls inside a visible board, that row gets a red line, and a booking that covers it gets a red ring. In the 7-day view the day headers alternate blue and teal, and the header whose date is `today` is orange.
- `days` defaults to 1. The **7 days** toggle calls `get_schedule` with `days=7`. Each day is its own table: an Indonesian header such as `Sabtu, 07 November 2026` (`Senin` through `Minggu`, `Januari` through `Desember`), then `JAM` and the room columns. The board scrolls horizontally. The first day's time column sticks to the left, and the date and room headers stick to the top.
- There is no "Not Available" row. Blocking stays on the website until a later change.

Set the hours under **Settings → Technical → System Parameters** (developer mode), or:

```python
params = env['ir.config_parameter'].sudo()
params.set_float('fav_booking.schedule_start_hour', 10)
params.set_float('fav_booking.schedule_end_hour', 26)
```

The parameter records are created with `noupdate`, so a later module upgrade does not put the defaults back over a value you changed. Reload the browser after `-u fav_booking` so the board assets refresh.
