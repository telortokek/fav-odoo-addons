/** @odoo-module */

import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const FLOOR_KEY = "fav_booking.schedule_floor_id";
const MODE_KEY = "fav_booking.schedule_mode";

export class FavSchedule extends Component {
    static template = "fav_booking.Schedule";
    props = useProps({
        ...standardActionServiceProps,
    });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const storedFloor = window.localStorage.getItem(FLOOR_KEY);
        const storedMode = window.localStorage.getItem(MODE_KEY);
        this.state = proxy({
            day: this.todayString(),
            floorId: storedFloor ? Number(storedFloor) : false,
            mode: storedMode === "week" ? "week" : "day",
            data: null,
        });
        onWillStart(() => this.load());
    }

    todayString() {
        const now = new Date();
        const month = String(now.getMonth() + 1).padStart(2, "0");
        const day = String(now.getDate()).padStart(2, "0");
        return `${now.getFullYear()}-${month}-${day}`;
    }

    async load() {
        const data = await this.orm.call("fav.booking", "get_schedule", [], {
            day: this.state.day,
            floor_id: this.state.floorId || false,
            days: this.state.mode === "week" ? 7 : 1,
        });
        this.state.data = data;
        this.state.day = data.day;
        this.state.floorId = data.floor_id || false;
        if (data.floor_id) {
            window.localStorage.setItem(FLOOR_KEY, String(data.floor_id));
        }
    }

    shiftDay(days) {
        const current = new Date(`${this.state.day}T00:00:00`);
        current.setDate(current.getDate() + days);
        const month = String(current.getMonth() + 1).padStart(2, "0");
        const day = String(current.getDate()).padStart(2, "0");
        this.state.day = `${current.getFullYear()}-${month}-${day}`;
        this.load();
    }

    prevDay() {
        this.shiftDay(this.state.mode === "week" ? -7 : -1);
    }

    nextDay() {
        this.shiftDay(this.state.mode === "week" ? 7 : 1);
    }

    goToday() {
        this.state.day = this.todayString();
        this.load();
    }

    onDate(event) {
        this.state.day = event.target.value;
        this.load();
    }

    onFloor(event) {
        this.state.floorId = Number(event.target.value);
        window.localStorage.setItem(FLOOR_KEY, String(this.state.floorId));
        this.load();
    }

    setMode(mode) {
        this.state.mode = mode;
        window.localStorage.setItem(MODE_KEY, mode);
        this.load();
    }

    get rooms() {
        return this.state.data?.rooms || [];
    }

    get slots() {
        return this.state.data?.slots || [];
    }

    get boards() {
        const boards = this.state.data?.boards || [];
        return boards.map((board) => {
            const byStart = {};
            const covered = {};
            for (const booking of board.bookings) {
                byStart[`${booking.room_id}:${booking.slot_index}`] = booking;
                for (let offset = 1; offset < booking.slot_span; offset++) {
                    covered[`${booking.room_id}:${booking.slot_index + offset}`] = true;
                }
            }
            return { ...board, byStart, covered };
        });
    }

    cell(board, roomId, index) {
        const key = `${roomId}:${index}`;
        const booking = board.byStart[key];
        if (booking) {
            return { show: true, empty: false, ...booking };
        }
        if (board.covered[key]) {
            return { show: false, empty: false };
        }
        return { show: false, empty: true };
    }

    openBooking(booking) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: booking.name,
            res_model: "fav.booking",
            res_id: booking.id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("fav_booking.schedule", FavSchedule);
