// Copyright (c) 2026, VFG and contributors

frappe.ui.form.on("Short Leave", {
	refresh(frm) {
		setup_approver_options(frm);
		setup_approval_buttons(frm);
		setup_attendance_sync(frm);
		set_field_read_only(frm);
		show_variance_indicator(frm);
	},

	approver_label(frm) {
		sync_approver_user(frm);
	},

	going_time(frm) {
		calculate_hours_preview(frm);
	},

	return_time(frm) {
		calculate_hours_preview(frm);
	},

	leave_date(frm) {
		calculate_hours_preview(frm);
	},
});

function setup_approver_options(frm) {
	if (frm.is_new() || frm.doc.docstatus === 0) {
		frappe.call({
			method: "hr_vfg.hr_ventureforce_global.doctype.short_leave.short_leave.get_short_leave_approver_options",
			callback(r) {
				const rows = r.message || [];
				if (!rows.length) return;
				const labels = rows.map((row) => row.label).join("\n");
				frm.set_df_property("approver_label", "options", labels);
				frm._approver_map = Object.fromEntries(rows.map((row) => [row.label, row.user]));
				if (frm.doc.approver_label) {
					sync_approver_user(frm);
				}
			},
		});
	}
}

function sync_approver_user(frm) {
	const user = (frm._approver_map || {})[frm.doc.approver_label];
	if (user) {
		frm.set_value("approver", user);
	}
}

function calculate_hours_preview(frm) {
	if (!frm.doc.going_time || !frm.doc.return_time || !frm.doc.leave_date) return;
	const start = frappe.datetime.str_to_obj(`${frm.doc.leave_date} ${frm.doc.going_time}`);
	const end = frappe.datetime.str_to_obj(`${frm.doc.leave_date} ${frm.doc.return_time}`);
	if (end <= start) return;
	const hours = (end - start) / (1000 * 60 * 60);
	frm.set_value("hours", flt(hours, 2));
}

function set_field_read_only(frm) {
	const pending = frm.doc.approval_status === "Pending Approval" && frm.doc.docstatus === 1;
	const closed = ["Approved", "Rejected"].includes(frm.doc.approval_status);
	frm.toggle_enable(["employee", "leave_date", "going_time", "return_time", "reason", "approver_label"], !pending && !closed);
}

function setup_attendance_sync(frm) {
	if (frm.doc.approval_status !== "Approved" || !frm.doc.name) return;

	frm.add_custom_button(__("Sync Attendance Punches"), () => {
		frappe.call({
			method: "hr_vfg.hr_ventureforce_global.doctype.short_leave.short_leave.sync_short_leave_attendance",
			args: { name: frm.doc.name },
			freeze: true,
			callback() {
				frm.reload_doc();
			},
		});
	}, __("Actions"));

	if (frm.doc.attendance_sync_status !== "Synced") {
		frappe.call({
			method: "hr_vfg.hr_ventureforce_global.doctype.short_leave.short_leave.sync_short_leave_attendance",
			args: { name: frm.doc.name, silent: 1 },
			callback() {
				frm.reload_doc();
			},
		});
	}
}

function show_variance_indicator(frm) {
	if (frm.doc.approval_status !== "Approved") return;

	if (frm.doc.exceeded_approved_time) {
		frm.dashboard.add_indicator(
			__("Exceeded approved time by {0} hour(s)", [flt(frm.doc.time_variance_hours, 2)]),
			"red"
		);
	} else if (frm.doc.attendance_sync_status === "Synced") {
		frm.dashboard.add_indicator(__("Actual punch time within approved limit"), "green");
	} else if (frm.doc.attendance_sync_status === "Partial") {
		frm.dashboard.add_indicator(__("Return punch not found yet"), "orange");
	} else if (frm.doc.attendance_sync_status === "Pending") {
		frm.dashboard.add_indicator(__("Waiting for attendance punches"), "blue");
	}
}

function setup_approval_buttons(frm) {
	if (frm.doc.docstatus !== 1 || frm.doc.approval_status !== "Pending Approval") return;
	if (frm.doc.approver !== frappe.session.user && frappe.session.user !== "Administrator") return;

	frm.add_custom_button(__("Approve"), () => {
		frappe.call({
			method: "hr_vfg.hr_ventureforce_global.doctype.short_leave.short_leave.approve_short_leave",
			args: { name: frm.doc.name },
			freeze: true,
			callback() {
				frm.reload_doc();
			},
		});
	}, __("Actions")).addClass("btn-primary");

	frm.add_custom_button(__("Reject"), () => {
		frappe.prompt(
			[
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: __("Rejection Remarks"),
					reqd: 1,
				},
			],
			(values) => {
				frappe.call({
					method: "hr_vfg.hr_ventureforce_global.doctype.short_leave.short_leave.reject_short_leave",
					args: { name: frm.doc.name, remarks: values.remarks },
					freeze: true,
					callback() {
						frm.reload_doc();
					},
				});
			},
			__("Reject Short Leave"),
			__("Reject")
		);
	}, __("Actions"));
}
