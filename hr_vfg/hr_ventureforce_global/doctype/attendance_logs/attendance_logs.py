# -*- coding: utf-8 -*-
# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import msgprint, _
from erpnext.utilities.transaction_base import TransactionBase
from frappe.model.naming import make_autoname
from frappe.utils import date_diff, getdate, add_days, today, cstr, get_time
from datetime import datetime
from datetime import timedelta
import datetime
import time

class AttendanceLogs(TransactionBase):
	def validate(self):
		# Live machine sync can insert punches into Attendance Logs without
		# rewriting Employee Attendance on every punch (handled by the full sync).
		if self.flags.get("skip_employee_attendance"):
			return
		self.get_employee_attendance()

	def get_employee_attendance(self,force_update=False):
		mon = ["January", "February", "March", "April", "May", "June", "July", 
		"August", "September", "October", "November", "December"]
		att_det = str(self.attendance).split()
		# Always derive period from attendance_date, not raw machine string.
		# For overnight checkouts we intentionally shift attendance_date to previous day,
		# so month/year lookup must follow attendance_date to avoid creating next-month doc.
		att_date = frappe.utils.getdate(self.attendance_date)
		month_ = mon[int(att_date.month)-1]

		start_date = frappe.utils.get_first_day(att_date)
		end_date = frappe.utils.get_last_day(att_date)
		
		
		hr_settings = frappe.get_single('V HR Settings')
		if hr_settings.period_from != 1:
			if att_date.day < hr_settings.period_from:
				tempDate  = att_date
				if (tempDate.month-1) ==0:
					start_date = frappe.utils.getdate(str(tempDate.year-1)+"-"+str((tempDate.month-1)+12)+"-"+str(hr_settings.period_from))
				else:
					start_date = frappe.utils.getdate(str(tempDate.year)+"-"+str((tempDate.month-1))+"-"+str(hr_settings.period_from))
				end_date = frappe.utils.getdate(str(tempDate.year)+"-"+str(tempDate.month)+"-"+str(hr_settings.period_to))
				month_ = mon[tempDate.month-1]
		
			else:
				tempDate  = att_date
				start_date = frappe.utils.getdate(str(tempDate.year)+"-"+str(tempDate.month)+"-"+str(hr_settings.period_from))
				if tempDate.month == 12:
					end_date = frappe.utils.getdate(str(tempDate.year+1)+"-"+str(1)+"-"+str(hr_settings.period_to))
				else:
					end_date = frappe.utils.getdate(str(tempDate.year)+"-"+str(tempDate.month+1)+"-"+str(hr_settings.period_to))
				month_ = mon[tempDate.month]
		
		year  = end_date.year
		total_days = int(date_diff(end_date, start_date))+1

		biometric_id = self.biometric_id or (att_det[1] if len(att_det) > 1 else None)
		empl = frappe.db.sql(
			""" select name, employee_name, branch, department, user_id from `tabEmployee` where biometric_id=%s""",
			biometric_id,
		)
		if empl:
			res = frappe.db.sql(""" select name from `tabEmployee Attendance` where employee=%s and month=%s and year=%s""",
						(empl[0][0], month_,year))
			if res:
				if self.type == "Check In":
					doc = frappe.get_doc("Employee Attendance", res[0][0])
					for x_ in range(len(doc.table1)):
						
						if doc.table1[x_].get("type") != None and doc.table1[x_].get("type") != "" and force_update==False:
							continue
						if str(doc.table1[x_].date) == self.attendance_date:
							doc.table1[x_].ip = self.ip
							doc.table1[x_].check_in_1 = self.attendance_time
							#frappe.db.sql("update `tabEmployee Attendance Table` set ip=%s, check_in_1=%s where name=%s",(self.ip,self.attendance_time,doc.table1[x_].name))
							break
					#frappe.db.commit()
					doc.save(ignore_permissions=True)
				elif self.type == "Check Out":
					doc = frappe.get_doc("Employee Attendance", res[0][0])
					for x_ in range(len(doc.table1)):
						if doc.table1[x_].get("type") != None and doc.table1[x_].get("type") != "" and force_update==False:
							continue
						if str(doc.table1[x_].date) == self.attendance_date:
							doc.table1[x_].ip = self.ip
							doc.table1[x_].check_out_1 = self.attendance_time
							#frappe.db.sql("update `tabEmployee Attendance Table` set ip=%s, check_out_1=%s where name=%s",(self.ip,self.attendance_time,doc.table1[x_].name))
							break
					#frappe.db.commit()
					doc.save(ignore_permissions=True)
			else:
				today = datetime.date.today()
				day_ = datetime.date(today.year, today.month, 1)
				single_day = datetime.timedelta(days=1)
				m=0
				f=0
				sat = 0
				sun = 0
				while day_.month == today.month:
					if day_.weekday() == 6:
						sun+=1
					elif day_.weekday() == 5:
						sat+=1
					elif day_.weekday() == 4:
						f+=1
					else:
						m+=1
					day_ += single_day

				doc = frappe.new_doc("Employee Attendance")
				doc.employee = empl[0][0]
				doc.employee_name = empl[0][1]
				doc.biometric_id = biometric_id
				doc.month = month_
				doc.year = year
				da = start_date
				doc.unit = empl[0][2]
				doc.department = empl[0][3]
				doc.email_id = empl[0][4]
				emp_meta = frappe.db.get_value(
					"Employee",
					empl[0][0],
					["holiday_list", "date_of_joining"],
					as_dict=True,
				) or {}
				doc.holiday_list = emp_meta.get("holiday_list")
				doc.joining_date = emp_meta.get("date_of_joining")
				#doc.total_working_hours = (int(empl[0][4])*m)+(int(empl[0][5])*f)+(int(empl[0][6])*sat)+(int(empl[0][7])*sun)
				for x in range(total_days):
					pi = doc.append('table1', {"check_in_1":None,"check_out_1":None})
					pi.date = da
					if str(da) == str(self.attendance_date):
						if self.type == "Check In":
							pi.check_in_1 = att_det[4]
						if self.type == "Check Out":
							pi.check_out_1 = att_det[4]
					else:
						pi.check_in_1 = hr_settings.auto_fetch_check_in
						pi.check_out_1 = hr_settings.auto_fetch_check_out
					da = da + timedelta(days=1)
				doc.save(ignore_permissions=True)



@frappe.whitelist()
def sync_attendance(**args):
	condition = """
		where attendance_date between '{0}' and '{1}'
	""".format(args.get("from_date"),args.get("to_date"))
	if args.get("employee"):
		condition+=" and biometric_id='{0}' ".format(frappe.db.get_value("Employee",{"name":args.get("employee")},"biometric_id"))
	elif args.get("department"):
		rec = frappe.db.get_all("Employee",filters = {"department":args.get("department")},fields=["biometric_id"])
		condition += " and biometric_id in {0}".format(tuple([r.biometric_id for r in rec]))
	data = frappe.db.sql("""select name from `tabAttendance Logs` {condition} """.format(condition=condition),as_dict=1)
	
	for item in data:
		try:
			frappe.get_doc("Attendance Logs",item.name).get_employee_attendance()
		except:
			frappe.log_error(frappe.get_traceback() ,"Attendance Sync")


def _checkout_target_date(employee, att_date, att_time):
	"""If checkout is before shift start, it belongs to the previous working day."""
	att_date = getdate(att_date)
	if not employee or not att_time:
		return att_date
	try:
		parts = str(att_time).split(":")
		punch = timedelta(hours=int(parts[0]), minutes=int(parts[1]))
	except Exception:
		return att_date

	assignment = frappe.db.sql(
		"""
		SELECT shift_type FROM `tabShift Assignment`
		WHERE employee=%s AND docstatus < 2 AND start_date <= %s
		  AND (end_date IS NULL OR end_date = '' OR end_date >= %s)
		ORDER BY start_date DESC, creation DESC
		LIMIT 1
		""",
		(employee, att_date, att_date),
		as_dict=True,
	)
	if not assignment:
		assignment = frappe.db.sql(
			"""
			SELECT shift_type FROM `tabShift Assignment`
			WHERE employee=%s AND docstatus < 2 AND start_date <= %s
			ORDER BY start_date DESC, creation DESC
			LIMIT 1
			""",
			(employee, att_date),
			as_dict=True,
		)
	if not assignment:
		return att_date
	start_time = frappe.db.get_value("Shift Type", assignment[0].shift_type, "start_time")
	if not start_time:
		return att_date
	start_s = str(start_time).split(":")
	shift_start = timedelta(hours=int(start_s[0]), minutes=int(start_s[1]))
	if punch < shift_start:
		return add_days(att_date, -1)
	return att_date


def _checkout_hour(att_time):
	try:
		return get_time(cstr(att_time)).hour
	except Exception:
		return 12


def _should_keep_checkout(existing_out, new_out, new_punch_dt, existing_punch_dt):
	"""Prefer evening outs over ZK ghost 00:00–04:59 replays.

	Legitimate after-midnight outs (hour < 5) are kept when no evening out exists.
	"""
	new_early = _checkout_hour(new_out) < 5
	if existing_out is None:
		return True
	ex_early = _checkout_hour(existing_out) < 5
	if new_early and not ex_early:
		return False
	if not new_early and ex_early:
		return True
	if new_punch_dt and existing_punch_dt:
		return new_punch_dt >= existing_punch_dt
	if new_punch_dt and not existing_punch_dt:
		return True
	return False


@frappe.whitelist()
def apply_logs_to_employee_attendance(from_date=None, to_date=None, biometric_ids=None):
	"""Rebuild check-in/out on Employee Attendance from Attendance Logs.

	Live machine sync stores punches but skips sheet updates. This copies first
	check-in and last check-out onto the monthly sheet and saves once per employee.

	After-midnight checkouts (before shift start) map to the previous day.
	Early 00:00–04:59 punches are ignored only when an evening checkout already
	exists for that day (ZK ghost replay) — not when they are the real out punch.
	"""
	from_date = getdate(from_date or add_days(today(), -1))
	to_date = getdate(to_date or today())
	if isinstance(biometric_ids, str):
		biometric_ids = frappe.parse_json(biometric_ids)

	# Include next day so 00:00–shift-start outs can map back into the range
	log_to = add_days(to_date, 1)
	log_filters = {"attendance_date": ["between", [str(from_date), str(log_to)]]}
	if biometric_ids:
		log_filters["biometric_id"] = ["in", biometric_ids]

	logs = frappe.get_all(
		"Attendance Logs",
		filters=log_filters,
		fields=["biometric_id", "attendance_date", "attendance_time", "type", "ip"],
		order_by="attendance_date, attendance_time",
	)
	if not logs:
		return {"updated": 0, "employees": 0}

	bio_to_emp = {}
	punches = {}  # (employee, date_str) -> {in, out, ip}

	for log in logs:
		bio = cstr(log.biometric_id)
		if bio not in bio_to_emp:
			bio_to_emp[bio] = frappe.db.get_value("Employee", {"biometric_id": bio}, "name")
		employee = bio_to_emp.get(bio)
		if not employee:
			continue

		calendar_date = getdate(log.attendance_date)
		att_time = cstr(log.attendance_time)
		log_type = cstr(log.type)
		try:
			punch_dt = datetime.datetime.combine(calendar_date, get_time(att_time))
		except Exception:
			punch_dt = None

		att_date = calendar_date
		if log_type == "Check Out":
			att_date = _checkout_target_date(employee, calendar_date, att_time)

		key = (employee, str(att_date))
		slot = punches.setdefault(key, {"check_in": None, "check_out": None, "ip": log.ip})
		if log_type == "Check In":
			prev = slot.get("check_in_dt")
			if slot["check_in"] is None or (punch_dt and (not prev or punch_dt < prev)):
				slot["check_in"] = att_time
				slot["check_in_dt"] = punch_dt
				slot["ip"] = log.ip
		elif log_type == "Check Out":
			if not _should_keep_checkout(
				slot.get("check_out"),
				att_time,
				punch_dt,
				slot.get("check_out_dt"),
			):
				continue
			slot["check_out"] = att_time
			slot["check_out_dt"] = punch_dt
			slot["ip"] = log.ip

	employees = sorted({emp for emp, _ in punches})
	updated_docs = 0
	updated_rows = 0
	errors = 0
	months = [
		"January", "February", "March", "April", "May", "June",
		"July", "August", "September", "October", "November", "December",
	]

	for employee in employees:
		# Cover month of from_date and to_date (overnight can shift a day back).
		month_keys = set()
		for d in (from_date, to_date, add_days(from_date, -1)):
			month_keys.add((months[d.month - 1], str(d.year)))
		ea_names = []
		for month_, year in month_keys:
			name = frappe.db.get_value(
				"Employee Attendance",
				{"employee": employee, "month": month_, "year": year},
				"name",
			)
			if name:
				ea_names.append(name)
		if not ea_names:
			continue

		for ea_name in ea_names:
			try:
				doc = frappe.get_doc("Employee Attendance", ea_name)
				changed = False
				for row in doc.table1:
					if cstr(row.get("type")) == "Adjustment":
						continue
					row_date = getdate(row.date)
					in_range = from_date <= row_date <= to_date
					slot = punches.get((employee, str(row.date)))
					if not slot and not in_range:
						continue
					ghost_out = False
					try:
						ghost_out = bool(
							row.check_out_1
							and _checkout_hour(row.check_out_1) < 5
							and not (slot and slot.get("check_out"))
						)
					except Exception:
						ghost_out = False
					if slot and slot["check_in"] and cstr(row.check_in_1) != slot["check_in"]:
						row.check_in_1 = slot["check_in"]
						row.ip = slot["ip"]
						changed = True
						updated_rows += 1
					if slot and slot["check_out"] and cstr(row.check_out_1) != slot["check_out"]:
						row.check_out_1 = slot["check_out"]
						row.ip = slot["ip"]
						changed = True
						updated_rows += 1
					elif ghost_out and in_range:
						row.check_out_1 = None
						changed = True
						updated_rows += 1
				if changed:
					doc.save(ignore_permissions=True)
					updated_docs += 1
					frappe.db.commit()
			except Exception:
				errors += 1
				frappe.db.rollback()
				frappe.log_error(frappe.get_traceback(), "Apply Attendance Logs")

	return {
		"updated": updated_docs,
		"rows": updated_rows,
		"employees": len(employees),
		"errors": errors,
		"from_date": str(from_date),
		"to_date": str(to_date),
	}