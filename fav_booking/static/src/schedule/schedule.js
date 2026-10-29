/** @odoo-module */

import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const FLOOR_KEY = "fav_booking.schedule_floor_id";

export class FavSchedule extends Component {
    static template = "fav_booking.Schedule";
    props = useProps({
        ...standardActionServiceProps,
    });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const stored = window.localStorage.getItem(FLOOR_KEY);
        this.state = proxy({
            day: this.todayString(),
            floorId: stored ? Number(stored) : false,
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
        this.shiftDay(-1);
    }

    nextDay() {
        this.shiftDay(1);
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

    formatHour(hour) {
        const normalized = ((hour % 24) + 24) % 24;
        const whole = Math.floor(normalized);
        const minutes = Math.round((normalized - whole) * 60);
        return `${String(whole).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
    }

    get slots() {
        const data = this.state.data;
        if (!data) {
            return [];
        }
        const slots = [];
        const step = data.slot_minutes / 60;
        for (let hour = data.open_hour; hour < data.close_hour - 0.001; hour += step) {
            slots.push({
                key: hour.toFixed(4),
                label: this.formatHour(hour),
                major: Math.abs(hour - Math.round(hour)) < 0.001,
            });
        }
        return slots;
    }

    get rooms() {
        const groups = this.state.data?.groups || [];
        return groups.flatMap((group) => group.rooms);
    }

    bookingsFor(roomId) {
        return (this.state.data?.bookings || []).filter((booking) => booking.room_id === roomId);
    }

    blockStyle(booking) {
        const total = this.state.data?.total_minutes || 1;
        const top = (booking.start_minute / total) * 100;
        const height = ((booking.end_minute - booking.start_minute) / total) * 100;
        return `top: ${top}%; height: ${Math.max(height, 2)}%;`;
    }

    paymentLabel(booking) {
        if (!booking.payment) {
            return "";
        }
        return booking.payment.toLocaleString(undefined, { maximumFractionDigits: 0 });
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

    openBill(booking) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "POS bill",
            res_model: "pos.order",
            res_id: booking.pos_order_id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("fav_booking.schedule", FavSchedule);
