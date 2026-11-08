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

    familyKey(room) {
        const type = `${room.room_type || ""} ${room.name || ""}`.toLowerCase();
        if (type.includes("vvip")) {
            return "vvip";
        }
        if (type.includes("deluxe")) {
            return "deluxe";
        }
        if (type.includes("suite")) {
            return "suite";
        }
        if (type.includes("vip")) {
            return "vip";
        }
        return "other";
    }

    palette(room) {
        const families = {
            vip: {
                heads: ["#dbeafe", "#bfdbfe", "#e0f2fe"],
                cells: ["#f8fbff", "#f3f8ff", "#f5fbff"],
                ink: "#1e3a8a",
            },
            vvip: {
                heads: ["#ede9fe", "#ddd6fe", "#f3e8ff"],
                cells: ["#faf8ff", "#f7f4ff", "#fdf9ff"],
                ink: "#5b21b6",
            },
            deluxe: {
                heads: ["#ccfbf1", "#99f6e4", "#d1fae5"],
                cells: ["#f4fffc", "#f0fdfa", "#f6fef9"],
                ink: "#115e59",
            },
            suite: {
                heads: ["#ffedd5", "#fed7aa", "#fef3c7"],
                cells: ["#fffaf5", "#fff7ed", "#fffdf5"],
                ink: "#9a3412",
            },
            other: {
                heads: ["#fce7f3", "#e0e7ff", "#dcfce7"],
                cells: ["#fff7fb", "#f8f9ff", "#f6fef8"],
                ink: "#334155",
            },
        };
        const key = this.familyKey(room);
        const family = families[key];
        const siblings = this.rooms.filter((item) => this.familyKey(item) === key);
        const shade = Math.max(siblings.findIndex((item) => item.id === room.id), 0) % family.heads.length;
        return {
            head: family.heads[shade],
            cell: family.cells[shade],
            ink: family.ink,
        };
    }

    roomHeadStyle(room) {
        const tone = this.palette(room);
        return `background-color: ${tone.head}; color: ${tone.ink};`;
    }

    roomCellStyle(room) {
        return `background-color: ${this.palette(room).cell};`;
    }

    nextDayString(day) {
        const current = new Date(`${day}T12:00:00`);
        current.setDate(current.getDate() + 1);
        const month = String(current.getMonth() + 1).padStart(2, "0");
        const date = String(current.getDate()).padStart(2, "0");
        return `${current.getFullYear()}-${month}-${date}`;
    }

    minutesOnBoard(day) {
        const data = this.state.data;
        if (!data || data.now_minute === undefined || data.now_minute === null) {
            return null;
        }
        if (day === data.today) {
            return data.now_minute;
        }
        if (data.today === this.nextDayString(day)) {
            return 1440 + data.now_minute;
        }
        return null;
    }

    isToday(day) {
        return Boolean(this.state.data) && day === this.state.data.today;
    }

    rowClass(board, slot) {
        const parts = [slot.start_minute % 60 === 0 ? "o_fav_on_hour" : "o_fav_half"];
        if (Math.floor(slot.start_minute / 60) % 2 === 1) {
            parts.push("o_fav_hour_alt");
        }
        if (this.slotIsNow(board, slot)) {
            parts.push("o_fav_now");
        }
        return parts.join(" ");
    }

    slotIsNow(board, slot) {
        const minutes = this.minutesOnBoard(board.day);
        if (minutes === null) {
            return false;
        }
        const length = this.state.data.slot_minutes || 30;
        return minutes >= slot.start_minute && minutes < slot.start_minute + length;
    }

    blockIsNow(board, booking) {
        const minutes = this.minutesOnBoard(board.day);
        const slot = this.slots[booking.slot_index];
        if (minutes === null || !slot) {
            return false;
        }
        const length = this.state.data.slot_minutes || 30;
        const start = slot.start_minute;
        return minutes >= start && minutes < start + booking.slot_span * length;
    }

    dateClass(board, index) {
        const parts = ["o_fav_date", index % 2 ? "o_fav_date_b" : "o_fav_date_a"];
        if (this.isToday(board.day)) {
            parts.push("o_fav_date_today");
        }
        return parts.join(" ");
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
