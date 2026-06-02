// Copyright (c) 2024, VFG and contributors
// For license information, please see license.txt

frappe.ui.form.on("Late Over Time", {
	get_data(frm) {
		frm.call({
			method: "get_data",
			doc: frm.doc,
			args: {},
			callback() {
				frm.reload_doc();
			},
		});
	},
});

function _toSecondsFromTime(t) {
	if (!t) return 0;
	const s = String(t).trim();
	if (!s) return 0;
	const parts = s.split(":").map((x) => parseFloat(x));
	if (parts.some((n) => !Number.isFinite(n))) return 0;
	while (parts.length < 3) parts.push(0);
	const [h, m, sec] = parts;
	return Math.max(0, Math.round(h * 3600 + m * 60 + sec));
}

function _toTimeStringFromSeconds(totalSeconds) {
	let s = Math.max(0, Math.round(Number(totalSeconds) || 0));
	const h = Math.floor(s / 3600);
	s -= h * 3600;
	const m = Math.floor(s / 60);
	s -= m * 60;
	const sec = s;
	const pad2 = (n) => String(n).padStart(2, "0");
	return `${pad2(h)}:${pad2(m)}:${pad2(sec)}`;
}

function _timeOnToday(timeVal) {
	if (!timeVal) return null;
	const raw = String(timeVal).trim();
	if (!raw) return null;
	const parts = raw.split(":").map((x) => parseFloat(x));
	while (parts.length < 3) parts.push(0);
	const d = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	d.setHours(parts[0] || 0, parts[1] || 0, parts[2] || 0, 0);
	return d;
}

function _calcOvertimeSecondsFromCheckout(row) {
	const co = _timeOnToday(row.check_out);
	if (!co) return 0;

	if (row.day_type === "Weekly Off" && row.check_in) {
		const ci = _timeOnToday(row.check_in);
		if (!ci) return 0;
		let checkout = new Date(co);
		const checkin = new Date(ci);
		if (checkout < checkin) checkout.setDate(checkout.getDate() + 1);
		return Math.max(0, Math.round((checkout - checkin) / 1000));
	}

	if (!row.shift_out) return 0;
	const so = _timeOnToday(row.shift_out);
	if (!so) return 0;

	let shiftOut = new Date(so);
	if (row.shift_in) {
		const si = _timeOnToday(row.shift_in);
		if (si && shiftOut < si) shiftOut.setDate(shiftOut.getDate() + 1);
	}

	let checkout = new Date(co);
	if (row.check_in) {
		const ci = _timeOnToday(row.check_in);
		if (ci && checkout < ci) checkout.setDate(checkout.getDate() + 1);
	}

	if (checkout <= shiftOut) return 0;
	return Math.max(0, Math.round((checkout - shiftOut) / 1000));
}

function _recalcApprovedOvertimeForRow(cdt, cdn) {
	const row = locals[cdt] && locals[cdt][cdn];
	if (!row) return;
	const otSeconds = _calcOvertimeSecondsFromCheckout(row);
	frappe.model.set_value(cdt, cdn, "late_sitting", _toTimeStringFromSeconds(otSeconds));
	frappe.model.set_value(cdt, cdn, "approved_overtime", _toTimeStringFromSeconds(otSeconds * 1.5));
}

frappe.ui.form.on("Overtime Form CT", {
	check_out(frm, cdt, cdn) {
		_recalcApprovedOvertimeForRow(cdt, cdn);
	},
});
