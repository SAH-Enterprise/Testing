# Copyright (c) 2026, VFG and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
	add_to_date,
	flt,
	get_datetime,
	getdate,
	now_datetime,
	time_diff_in_hours,
)

from hr_vfg.hr_ventureforce_global.doctype.short_leave_settings.short_leave_settings import (
	get_approver_map,
	get_short_leave_settings,
)


class ShortLeave(Document):
	def validate(self):
		self._set_approver_user()
		self._calculate_hours()
		self._validate_hours_limit()
		self._validate_monthly_limit()
		if self.approval_status == "Approved" and self.docstatus == 1:
			sync_actual_punch_from_logs(self, save=False)

	def before_submit(self):
		if not self.approver:
			frappe.throw(_("Select an approver in Approval From."))
		if self.approval_status not in ("Draft", ""):
			frappe.throw(_("This short leave has already been processed."))

	def on_submit(self):
		self.db_set("approval_status", "Pending Approval", update_modified=False)
		self.notify_approver()

	def _set_approver_user(self):
		if not self.approver_label:
			return
		approver_map = get_approver_map()
		user = approver_map.get(self.approver_label)
		if not user:
			frappe.throw(
				_("Approver {0} is not configured. Open Short Leave Settings and link a User.").format(
					self.approver_label
				)
			)
		self.approver = user

	def _calculate_hours(self):
		if self.going_time and self.return_time:
			start = get_datetime(f"{self.leave_date} {self.going_time}")
			end = get_datetime(f"{self.leave_date} {self.return_time}")
			if end <= start:
				frappe.throw(_("Approved Return Time must be after Approved Going Time."))
			self.hours = round(time_diff_in_hours(end, start), 2)
		elif self.going_time:
			settings = get_short_leave_settings()
			self.hours = flt(settings.max_hours_per_short_leave) or 0

	def _validate_hours_limit(self):
		settings = get_short_leave_settings()
		max_hours = flt(settings.max_hours_per_short_leave)
		if max_hours and self.hours and self.hours > max_hours:
			frappe.throw(_("Short leave cannot exceed {0} hour(s).").format(max_hours))

	def _validate_monthly_limit(self):
		if not self.employee or not self.leave_date:
			return
		settings = get_short_leave_settings()
		max_count = frappe.utils.cint(settings.max_short_leaves_per_month)
		if not max_count:
			return

		month_start = frappe.utils.get_first_day(self.leave_date)
		month_end = frappe.utils.get_last_day(self.leave_date)
		existing = frappe.db.count(
			"Short Leave",
			{
				"employee": self.employee,
				"leave_date": ["between", [month_start, month_end]],
				"approval_status": ["in", ["Pending Approval", "Approved"]],
				"docstatus": 1,
				"name": ["!=", self.name],
			},
		)
		if existing >= max_count:
			frappe.throw(_("Monthly short leave limit ({0}) reached for this employee.").format(max_count))

	def notify_approver(self):
		if not self.approver:
			return
		frappe.sendmail(
			recipients=[self.approver],
			subject=_("Short Leave Approval: {0}").format(self.employee_name or self.employee),
			message=_(
				"{0} requested short leave on {1} from {2}.<br>Reason: {3}<br><br>"
				"<a href='{4}'>Open Short Leave</a>"
			).format(
				self.employee_name or self.employee,
				frappe.format(self.leave_date, {"fieldtype": "Date"}),
				self.going_time,
				self.reason or "",
				frappe.utils.get_url_to_form("Short Leave", self.name),
			),
		)


def sync_actual_punch_from_logs(doc, save=True):
	"""Match Check Out / Check In punches from Attendance Logs for approved short leave."""
	if doc.approval_status != "Approved" or not doc.employee or not doc.leave_date or not doc.going_time:
		if doc.approval_status != "Approved":
			doc.attendance_sync_status = "Pending"
		return doc

	settings = get_short_leave_settings()
	grace_before = frappe.utils.cint(getattr(settings, "punch_grace_minutes_before", None) or 15)
	grace_after = frappe.utils.cint(getattr(settings, "punch_grace_minutes_after", None) or 60)

	biometric_id = frappe.db.get_value("Employee", doc.employee, "biometric_id")
	if not biometric_id:
		doc.attendance_sync_status = "Not Found"
		_clear_actual_fields(doc)
		if save and doc.name:
			_save_actual_fields(doc)
		return doc

	approved_start = get_datetime(f"{doc.leave_date} {doc.going_time}")
	if doc.return_time:
		approved_end = get_datetime(f"{doc.leave_date} {doc.return_time}")
	else:
		approved_end = add_to_date(approved_start, hours=flt(doc.hours) or flt(settings.max_hours_per_short_leave) or 2)

	window_start = add_to_date(approved_start, minutes=-grace_before)
	window_end = add_to_date(approved_end, minutes=grace_after)
	leave_date_str = str(getdate(doc.leave_date))

	logs = frappe.db.sql(
		"""
		SELECT name, attendance_time, attendance_date, type
		FROM `tabAttendance Logs`
		WHERE biometric_id = %s
			AND LEFT(attendance_date, 10) = %s
		ORDER BY attendance_time ASC
		""",
		(biometric_id, leave_date_str),
		as_dict=True,
	)

	checkouts = [_parse_log_row(row) for row in logs if row.type == "Check Out"]
	checkins = [_parse_log_row(row) for row in logs if row.type == "Check In"]
	checkouts = [row for row in checkouts if row]
	checkins = [row for row in checkins if row]

	going_log = _find_going_punch(checkouts, approved_start, window_start, window_end)
	return_log = _find_return_punch(checkins, going_log, approved_end, window_end)

	if going_log:
		doc.actual_going_time = going_log["time"].strftime("%H:%M:%S")
		doc.actual_going_log = going_log["name"]
	else:
		doc.actual_going_time = None
		doc.actual_going_log = None

	if return_log:
		doc.actual_return_time = return_log["time"].strftime("%H:%M:%S")
		doc.actual_return_log = return_log["name"]
	else:
		doc.actual_return_time = None
		doc.actual_return_log = None

	if going_log and return_log:
		doc.actual_hours = round(time_diff_in_hours(return_log["time"], going_log["time"]), 2)
		doc.time_variance_hours = round(flt(doc.actual_hours) - flt(doc.hours), 2)
		doc.exceeded_approved_time = 1 if flt(doc.time_variance_hours) > 0 else 0
		doc.attendance_sync_status = "Synced"
	elif going_log:
		doc.actual_hours = 0
		doc.time_variance_hours = 0
		doc.exceeded_approved_time = 0
		doc.attendance_sync_status = "Partial"
	else:
		_clear_actual_hours(doc)
		doc.attendance_sync_status = "Not Found" if logs else "Pending"

	if save and doc.name:
		_save_actual_fields(doc)

	return doc


def _parse_log_row(row):
	try:
		date_str = str(row.attendance_date)[:10]
		time_str = str(row.attendance_time).strip()
		log_dt = get_datetime(f"{date_str} {time_str}")
		return {"name": row.name, "time": log_dt, "raw": row}
	except Exception:
		return None


def _find_going_punch(checkouts, approved_start, window_start, window_end):
	"""First Check Out at/after approved going time within window."""
	candidates = [
		row
		for row in checkouts
		if window_start <= row["time"] <= window_end and row["time"] >= add_to_date(approved_start, minutes=-1)
	]
	if candidates:
		return min(candidates, key=lambda row: abs((row["time"] - approved_start).total_seconds()))

	# Fallback: closest Check Out in window
	window_checkouts = [row for row in checkouts if window_start <= row["time"] <= window_end]
	if window_checkouts:
		return min(window_checkouts, key=lambda row: abs((row["time"] - approved_start).total_seconds()))
	return None


def _find_return_punch(checkins, going_log, approved_end, window_end):
	if not going_log:
		return None

	candidates = [
		row
		for row in checkins
		if row["time"] > going_log["time"] and row["time"] <= window_end
	]
	if not candidates:
		return None

	# Prefer first Check In after going punch, closest to approved return
	return min(candidates, key=lambda row: (row["time"] - going_log["time"]).total_seconds())


def _clear_actual_fields(doc):
	doc.actual_going_time = None
	doc.actual_return_time = None
	doc.actual_going_log = None
	doc.actual_return_log = None
	_clear_actual_hours(doc)


def _clear_actual_hours(doc):
	doc.actual_hours = 0
	doc.time_variance_hours = 0
	doc.exceeded_approved_time = 0


def _save_actual_fields(doc):
	frappe.db.set_value(
		"Short Leave",
		doc.name,
		{
			"actual_going_time": doc.actual_going_time,
			"actual_return_time": doc.actual_return_time,
			"actual_hours": doc.actual_hours,
			"time_variance_hours": doc.time_variance_hours,
			"exceeded_approved_time": doc.exceeded_approved_time,
			"attendance_sync_status": doc.attendance_sync_status,
			"actual_going_log": doc.actual_going_log,
			"actual_return_log": doc.actual_return_log,
		},
		update_modified=False,
	)


@frappe.whitelist()
def sync_short_leave_attendance(name, silent=0):
	doc = frappe.get_doc("Short Leave", name)
	if doc.approval_status != "Approved":
		frappe.throw(_("Attendance can only be synced for approved short leave requests."))
	sync_actual_punch_from_logs(doc, save=True)
	if not frappe.utils.cint(silent):
		frappe.msgprint(_("Attendance punches synced from Attendance Logs."), indicator="green")
	return {
		"attendance_sync_status": doc.attendance_sync_status,
		"actual_going_time": doc.actual_going_time,
		"actual_return_time": doc.actual_return_time,
		"actual_hours": doc.actual_hours,
		"time_variance_hours": doc.time_variance_hours,
		"exceeded_approved_time": doc.exceeded_approved_time,
	}


def sync_all_pending_short_leaves():
	"""Scheduled job: sync approved short leaves for today and past 7 days."""
	from frappe.utils import add_days, today

	start_date = add_days(today(), -7)
	names = frappe.get_all(
		"Short Leave",
		filters={
			"docstatus": 1,
			"approval_status": "Approved",
			"leave_date": [">=", start_date],
			"attendance_sync_status": ["in", ["Pending", "Partial", "Not Found"]],
		},
		pluck="name",
	)
	for name in names:
		try:
			doc = frappe.get_doc("Short Leave", name)
			sync_actual_punch_from_logs(doc, save=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Short Leave attendance sync failed for {name}")


def on_attendance_log_update(doc, method=None):
	"""Re-sync short leave when employee punches in/out."""
	if not doc.biometric_id or not doc.attendance_date:
		return

	employee = frappe.db.get_value("Employee", {"biometric_id": doc.biometric_id}, "name")
	if not employee:
		return

	leave_date = str(getdate(str(doc.attendance_date)[:10]))
	short_leaves = frappe.get_all(
		"Short Leave",
		filters={
			"employee": employee,
			"leave_date": leave_date,
			"approval_status": "Approved",
			"docstatus": 1,
		},
		pluck="name",
	)
	for name in short_leaves:
		try:
			sl_doc = frappe.get_doc("Short Leave", name)
			sync_actual_punch_from_logs(sl_doc, save=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Short Leave punch sync failed for {name}")


@frappe.whitelist()
def approve_short_leave(name, remarks=None):
	doc = frappe.get_doc("Short Leave", name)
	_ensure_approver(doc)
	if doc.approval_status != "Pending Approval":
		frappe.throw(_("Only pending requests can be approved."))

	doc.approval_status = "Approved"
	doc.approved_by = frappe.session.user
	doc.approval_date = now_datetime()
	doc.attendance_sync_status = "Pending"
	if remarks:
		doc.add_comment("Comment", remarks)
	doc.save(ignore_permissions=True)
	sync_actual_punch_from_logs(doc, save=True)
	frappe.msgprint(_("Short Leave approved."), indicator="green")
	return doc.name


@frappe.whitelist()
def reject_short_leave(name, remarks=None):
	if not remarks:
		frappe.throw(_("Rejection remarks are required."))

	doc = frappe.get_doc("Short Leave", name)
	_ensure_approver(doc)
	if doc.approval_status != "Pending Approval":
		frappe.throw(_("Only pending requests can be rejected."))

	doc.approval_status = "Rejected"
	doc.rejection_remarks = remarks
	doc.approved_by = frappe.session.user
	doc.approval_date = now_datetime()
	doc.save(ignore_permissions=True)
	frappe.msgprint(_("Short Leave rejected."), indicator="orange")
	return doc.name


@frappe.whitelist()
def get_short_leave_approver_options():
	"""Return approver labels and linked users for the form."""
	settings = get_short_leave_settings()
	return [
		{"label": row.approver_label, "user": row.user}
		for row in (settings.get("short_leave_approvers") or [])
		if row.approver_label
	]


def _ensure_approver(doc):
	if frappe.session.user == "Administrator":
		return
	if doc.approver != frappe.session.user:
		frappe.throw(_("Only the selected approver can approve or reject this request."))
