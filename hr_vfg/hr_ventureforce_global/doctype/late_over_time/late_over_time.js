// Copyright (c) 2024, VFG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Late Over Time', {
	// refresh: function(frm) {

	// }
	get_data(frm){
		frm.call({
			method:"get_data",
			doc:frm.doc,
			args:{
				
			},
			callback:function(r){
				//frm.save()
				frm.reload_doc()
			}
		})
	}
});

function _toSecondsFromTime(t) {
	if (!t) return 0;
	const s = String(t).trim();
	if (!s) return 0;
	const parts = s.split(":").map((x) => parseInt(x, 10));
	if (parts.some((n) => !Number.isFinite(n))) return 0;
	while (parts.length < 3) parts.push(0);
	const [h, m, sec] = parts;
	return (h * 3600) + (m * 60) + sec;
}

function _toTimeStringFromSeconds(totalSeconds) {
	let s = Math.max(0, Math.round(Number(totalSeconds) || 0));
	const h = Math.floor(s / 3600); s -= h * 3600;
	const m = Math.floor(s / 60); s -= m * 60;
	const sec = s;
	const pad2 = (n) => String(n).padStart(2, "0");
	return `${pad2(h)}:${pad2(m)}:${pad2(sec)}`;
}

function _recalcApprovedOvertimeForRow(cdt, cdn) {
	const row = locals[cdt] && locals[cdt][cdn];
	if (!row) return;
	const lateSittingSeconds = _toSecondsFromTime(row.late_sitting);
	const approvedSeconds = lateSittingSeconds * 1.5;
	frappe.model.set_value(cdt, cdn, "approved_overtime", _toTimeStringFromSeconds(approvedSeconds));
}

frappe.ui.form.on("Overtime Form CT", {
	late_sitting(frm, cdt, cdn) {
		_recalcApprovedOvertimeForRow(cdt, cdn);
	},
});
