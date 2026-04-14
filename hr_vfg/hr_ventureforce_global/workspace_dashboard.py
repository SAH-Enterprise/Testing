from datetime import date

import frappe
from frappe.utils import add_months, getdate, nowdate


def _month_key(value):
	return value.strftime("%Y-%m")


def _month_start(value):
	return value.replace(day=1)


def _month_label(month_key):
	year, month = month_key.split("-")
	return f"{date(int(year), int(month), 1):%b %Y}"


def _to_float(value):
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def _time_or_number_to_hours(value):
	if value in (None, ""):
		return 0.0

	if isinstance(value, (int, float)):
		return float(value)

	text = str(value).strip()
	if not text:
		return 0.0

	if ":" in text:
		parts = text.split(":")
		try:
			hours = float(parts[0] or 0)
			minutes = float(parts[1] or 0) if len(parts) > 1 else 0
			seconds = float(parts[2] or 0) if len(parts) > 2 else 0
			return hours + (minutes / 60.0) + (seconds / 3600.0)
		except (TypeError, ValueError):
			return 0.0

	try:
		return float(text)
	except (TypeError, ValueError):
		return 0.0


@frappe.whitelist()
def get_hr_attendance_overtime_workspace_data():
	today = getdate(nowdate())
	current_month = _month_start(today)
	start_month = add_months(current_month, -5)
	end_date = today

	months = []
	cursor = start_month
	while cursor <= current_month:
		months.append(_month_key(cursor))
		cursor = add_months(cursor, 1)

	attendance_map = {
		month: {
			"attendance_docs": 0,
			"present_days": 0.0,
			"overtime_hours": 0.0,
			"approved_overtime_hours": 0.0,
			"late_marks": 0.0,
			"absents": 0.0,
			"early_goings": 0.0,
			"missed_check_in": 0.0,
			"missed_check_out": 0.0,
		}
		for month in months
	}
	late_ot_map = {
		month: {
			"requests": 0,
			"total_hours": 0.0,
			"approved_hours": 0.0,
		}
		for month in months
	}

	attendance_rows = frappe.db.sql(
		"""
			select
				date_format(str_to_date(concat(`year`, '-', `month`, '-01'), '%%Y-%%M-%%d'), '%%Y-%%m') as month_key,
				count(name) as attendance_docs,
				sum(cast(coalesce(nullif(present_days, ''), '0') as decimal(18,2))) as present_days,
				sum(cast(coalesce(nullif(over_time, ''), '0') as decimal(18,2))) as overtime_hours,
				sum(cast(coalesce(nullif(approved_overtime_le, ''), '0') as decimal(18,2))) as approved_overtime_hours,
				sum(cast(coalesce(nullif(total_lates, ''), '0') as decimal(18,2))) as late_marks,
				sum(cast(coalesce(nullif(total_absents, ''), '0') as decimal(18,2))) as absents,
				sum(cast(coalesce(nullif(total_early_goings, ''), '0') as decimal(18,2))) as early_goings,
				sum(cast(coalesce(nullif(total_absent_check_in_missing, ''), '0') as decimal(18,2))) as missed_check_in,
				sum(cast(coalesce(nullif(total_absent_missing_check_out, ''), '0') as decimal(18,2))) as missed_check_out
			from `tabEmployee Attendance`
		where str_to_date(concat(`year`, '-', `month`, '-01'), '%%Y-%%M-%%d') between %s and %s
		group by month_key
		order by month_key asc
		""",
		[start_month, end_date],
		as_dict=True,
	)

	for row in attendance_rows:
		month_key = row.month_key
		if month_key not in attendance_map:
			continue
		attendance_map[month_key] = {
			"attendance_docs": int(row.attendance_docs or 0),
			"present_days": round(_to_float(row.present_days), 2),
			"overtime_hours": round(_to_float(row.overtime_hours), 2),
			"approved_overtime_hours": round(_to_float(row.approved_overtime_hours), 2),
			"late_marks": round(_to_float(row.late_marks), 2),
			"absents": round(_to_float(row.absents), 2),
			"early_goings": round(_to_float(row.early_goings), 2),
			"missed_check_in": round(_to_float(row.missed_check_in), 2),
			"missed_check_out": round(_to_float(row.missed_check_out), 2),
		}

	late_ot_rows = frappe.db.sql(
		"""
		select date, total_over_time, approved_over_time
		from `tabLate Over Time`
		where ifnull(docstatus, 0) < 2
		  and date between %s and %s
		order by date asc
		""",
		[start_month, end_date],
		as_dict=True,
	)

	for row in late_ot_rows:
		if not row.date:
			continue
		month_key = _month_key(_month_start(getdate(row.date)))
		if month_key not in late_ot_map:
			continue
		late_ot_map[month_key]["requests"] += 1
		late_ot_map[month_key]["total_hours"] += _time_or_number_to_hours(row.total_over_time)
		late_ot_map[month_key]["approved_hours"] += _time_or_number_to_hours(row.approved_over_time)

	for month_key, values in late_ot_map.items():
		values["total_hours"] = round(values["total_hours"], 2)
		values["approved_hours"] = round(values["approved_hours"], 2)

	current_key = _month_key(current_month)
	current_attendance = attendance_map[current_key]
	current_late_ot = late_ot_map[current_key]

	department_rows = frappe.db.sql(
		"""
		select
			coalesce(nullif(department, ''), 'Unassigned') as department,
			sum(cast(coalesce(nullif(present_days, ''), '0') as decimal(18,2))) as present_days,
			sum(cast(coalesce(nullif(total_working_days, ''), '0') as decimal(18,2))) as working_days,
			sum(cast(coalesce(nullif(total_lates, ''), '0') as decimal(18,2))) as late_marks,
			sum(cast(coalesce(nullif(total_absents, ''), '0') as decimal(18,2))) as absents,
			sum(cast(coalesce(nullif(over_time, ''), '0') as decimal(18,2))) as overtime_hours,
			sum(cast(coalesce(nullif(approved_overtime_le, ''), '0') as decimal(18,2))) as approved_overtime_hours
		from `tabEmployee Attendance`
		where str_to_date(concat(`year`, '-', `month`, '-01'), '%%Y-%%M-%%d') = %s
		group by department
		order by present_days desc, overtime_hours desc
		limit 8
		""",
		[current_month],
		as_dict=True,
	)

	department_labels = []
	department_present_rate = []
	department_overtime_hours = []
	department_late_marks = []
	department_absents = []

	for row in department_rows:
		present_days = _to_float(row.present_days)
		working_days = _to_float(row.working_days)
		present_rate = round((present_days / working_days) * 100, 2) if working_days else 0.0
		department_labels.append(row.department)
		department_present_rate.append(present_rate)
		department_overtime_hours.append(round(_to_float(row.overtime_hours), 2))
		department_late_marks.append(round(_to_float(row.late_marks), 2))
		department_absents.append(round(_to_float(row.absents), 2))

	return {
		"months": [_month_label(month) for month in months],
		"attendance_docs": [attendance_map[month]["attendance_docs"] for month in months],
		"present_days": [attendance_map[month]["present_days"] for month in months],
		"attendance_overtime_hours": [attendance_map[month]["overtime_hours"] for month in months],
		"approved_overtime_hours": [attendance_map[month]["approved_overtime_hours"] for month in months],
		"late_marks": [attendance_map[month]["late_marks"] for month in months],
		"absents": [attendance_map[month]["absents"] for month in months],
		"early_goings": [attendance_map[month]["early_goings"] for month in months],
		"missed_check_in": [attendance_map[month]["missed_check_in"] for month in months],
		"missed_check_out": [attendance_map[month]["missed_check_out"] for month in months],
		"late_ot_requests": [late_ot_map[month]["requests"] for month in months],
		"late_ot_total_hours": [late_ot_map[month]["total_hours"] for month in months],
		"late_ot_approved_hours": [late_ot_map[month]["approved_hours"] for month in months],
		"department_labels": department_labels,
		"department_present_rate": department_present_rate,
		"department_overtime_hours": department_overtime_hours,
		"department_late_marks": department_late_marks,
		"department_absents": department_absents,
		"kpis": {
			"month_label": _month_label(current_key),
			"attendance_docs": current_attendance["attendance_docs"],
			"present_days": current_attendance["present_days"],
			"attendance_overtime_hours": current_attendance["overtime_hours"],
			"approved_overtime_hours": current_attendance["approved_overtime_hours"],
			"late_marks": current_attendance["late_marks"],
			"absents": current_attendance["absents"],
			"early_goings": current_attendance["early_goings"],
			"missed_check_in": current_attendance["missed_check_in"],
			"missed_check_out": current_attendance["missed_check_out"],
			"late_ot_requests": current_late_ot["requests"],
			"late_ot_total_hours": current_late_ot["total_hours"],
			"late_ot_approved_hours": current_late_ot["approved_hours"],
		},
	}
