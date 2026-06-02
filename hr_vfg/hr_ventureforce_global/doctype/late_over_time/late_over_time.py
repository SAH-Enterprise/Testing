# Copyright (c) 2024, VFG and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
from datetime import datetime, timedelta


def _time_to_seconds(val):
	"""Parse HH:MM[:SS[.micro]] or timedelta to seconds."""
	if not val:
		return 0
	if isinstance(val, timedelta):
		return max(0, int(val.total_seconds()))
	if isinstance(val, str):
		raw = val.strip()
		if not raw:
			return 0
		parts = [p for p in raw.split(":") if p != ""]
		if not parts:
			return 0
		while len(parts) < 3:
			parts.append("0")
		try:
			h = int(float(parts[0]))
			m = int(float(parts[1]))
			s = float(parts[2])
		except (ValueError, TypeError):
			return 0
		return max(0, int(h * 3600 + m * 60 + s))
	return 0


def _seconds_to_time_str(seconds):
	sec = int(round(max(0, seconds)))
	h = sec // 3600
	sec = sec % 3600
	m = sec // 60
	s = sec % 60
	return f"{h:02d}:{m:02d}:{s:02d}"


def _time_on_date(val, base_date=None):
	"""Return datetime for a time value on base_date (default today)."""
	base_date = base_date or datetime.today().date()
	if isinstance(val, datetime):
		return val
	if isinstance(val, timedelta):
		return datetime.combine(base_date, (datetime.min + val).time())
	if isinstance(val, str):
		raw = val.strip()
		if not raw:
			return None
		for fmt in ("%H:%M:%S", "%H:%M"):
			try:
				return datetime.combine(base_date, datetime.strptime(raw, fmt).time())
			except ValueError:
				continue
	return None


def calc_overtime_seconds_from_checkout(check_out, shift_out=None, shift_in=None, check_in=None, day_type=None):
	"""OT duration after shift end (or full span on weekly off), from editable checkout."""
	co = _time_on_date(check_out)
	if not co:
		return 0

	if day_type == "Weekly Off" and check_in:
		ci = _time_on_date(check_in)
		if ci and co < ci:
			co += timedelta(days=1)
		return max(0, int((co - ci).total_seconds())) if ci else 0

	if not shift_out:
		return 0

	so = _time_on_date(shift_out)
	if not so:
		return 0

	if shift_in:
		si = _time_on_date(shift_in)
		if si and so < si:
			so += timedelta(days=1)

	if check_in:
		ci = _time_on_date(check_in)
		if ci and co < ci:
			co += timedelta(days=1)

	if co <= so:
		return 0
	return int((co - so).total_seconds())


class LateOverTime(Document):
	def validate(self):
		self.month_and_year()
		self.set_approved_overtime_from_checkout()
		self.total_ot()

	def set_approved_overtime_from_checkout(self):
		"""Approved OT from editable checkout: (checkout - shift end) * 1.5."""
		for row in self.details or []:
			shift_out = row.get("shift_out")
			shift_in = row.get("shift_in")
			check_in = row.get("check_in")
			day_type = row.get("day_type")

			if not shift_out and row.get("att_child_ref"):
				att = frappe.db.get_value(
					"Employee Attendance Table",
					row.att_child_ref,
					["shift_out", "shift_in", "check_in_1", "day_type"],
					as_dict=True,
				)
				if att:
					shift_out = shift_out or att.shift_out
					shift_in = shift_in or att.shift_in
					check_in = check_in or att.check_in_1
					day_type = day_type or att.day_type

			ot_seconds = calc_overtime_seconds_from_checkout(
				row.get("check_out"),
				shift_out=shift_out,
				shift_in=shift_in,
				check_in=check_in,
				day_type=day_type,
			)
			row.late_sitting = _seconds_to_time_str(ot_seconds)
			row.approved_overtime = _seconds_to_time_str(ot_seconds * 1.5)

	def month_and_year(self):
		date_str = str(self.date)
		date_obj = datetime.strptime(date_str, "%Y-%m-%d")
		self.day = date_obj.strftime("%A")
		self.months = date_obj.strftime("%B")
		self.year1 = date_obj.year

	def total_ot(self):
		total_seconds = 0
		total_approved_seconds = 0

		for row in self.details:
			total_seconds += _time_to_seconds(row.actual_overtime)
			total_approved_seconds += _time_to_seconds(row.approved_overtime)

		self.total_over_time = str(timedelta(seconds=total_seconds))
		self.approved_over_time = str(timedelta(seconds=total_approved_seconds))

	@frappe.whitelist()
	def get_data(self):
		rec = frappe.db.sql(
			"""
			select p.employee, p.employee_name, p.designation, c.estimated_late, c.late_sitting,
				c.check_in_1, c.check_out_1, c.shift_in, c.shift_out, c.day_type,
				c.approved_ot1, c.name as child_name, p.name as parent_name
			from `tabEmployee Attendance` p
			LEFT JOIN `tabEmployee Attendance Table` c ON c.parent=p.name
			where c.date=%s and estimated_late is not null
				and (c.approved_ot1 = '' or c.approved_ot1 is null or c.approved_ot1 = '00:00:00')
		""",
			(self.date,),
			as_dict=1,
		)

		if rec:
			self.details = []
			for r in rec:
				allow_ot = frappe.db.get_value("Employee", r.employee, "is_overtime_allowed")
				if allow_ot == 1 and r.estimated_late:
					self.append(
						"details",
						{
							"employee": r.employee,
							"actual_overtime": r.estimated_late,
							"late_sitting": r.late_sitting,
							"check_in": r.check_in_1,
							"check_out": r.check_out_1,
							"shift_in": r.shift_in,
							"shift_out": r.shift_out,
							"day_type": r.day_type,
							"approved_overtime": r.estimated_late,
							"employee_name": r.employee_name,
							"designation": r.designation,
							"att_ref": r.parent_name,
							"att_child_ref": r.child_name,
						},
					)
			self.set_approved_overtime_from_checkout()
			self.save()

	def on_submit(self):
		parent_docs = {}

		for r in self.details:
			# Only push approved OT to attendance; checkout stays as-is in attendance.
			frappe.db.sql(
				"update `tabEmployee Attendance Table` set approved_ot1=%s where name=%s",
				(r.approved_overtime, r.att_child_ref),
			)

			if r.att_ref not in parent_docs:
				parent_docs[r.att_ref] = []
			parent_docs[r.att_ref].append(
				{
					"child_ref": r.att_child_ref,
					"approved_ot1": r.approved_overtime,
				}
			)

		frappe.db.commit()

		for parent_name, updates in parent_docs.items():
			try:
				frappe.clear_cache(doctype="Employee Attendance")
				doc = frappe.get_doc("Employee Attendance", parent_name)
				doc.reload()

				for update in updates:
					child_row = doc.getone({"name": update["child_ref"]})
					if child_row:
						child_row.approved_ot1 = update["approved_ot1"]

				doc.save(ignore_permissions=True)
				frappe.db.commit()

			except Exception as e:
				frappe.log_error(
					f"Error updating Employee Attendance {parent_name} from Late Over Time: {str(e)}\n{frappe.get_traceback()}",
					"Late Over Time: Update Error",
				)
				frappe.db.rollback()
				frappe.throw(f"Error updating attendance for {parent_name}: {str(e)}")

	def on_cancel(self):
		parent_docs = {}

		for r in self.details:
			frappe.db.sql(
				"update `tabEmployee Attendance Table` set approved_ot1='' where name=%s",
				(r.att_child_ref,),
			)

			if r.att_ref not in parent_docs:
				parent_docs[r.att_ref] = []
			parent_docs[r.att_ref].append({"child_ref": r.att_child_ref})

		frappe.db.commit()

		for parent_name, updates in parent_docs.items():
			try:
				frappe.clear_cache(doctype="Employee Attendance")
				doc = frappe.get_doc("Employee Attendance", parent_name)
				doc.reload()

				for update in updates:
					child_row = doc.getone({"name": update["child_ref"]})
					if child_row:
						child_row.approved_ot1 = ""

				doc.save(ignore_permissions=True)
				frappe.db.commit()

			except Exception as e:
				frappe.log_error(
					f"Error updating Employee Attendance {parent_name} from Late Over Time (cancel): {str(e)}\n{frappe.get_traceback()}",
					"Late Over Time: Cancel Error",
				)
				frappe.db.rollback()
				frappe.throw(f"Error updating attendance for {parent_name}: {str(e)}")
