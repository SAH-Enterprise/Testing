import frappe
from frappe import _
from frappe.utils import getdate, nowdate


def _resolve_document_date(doc):
	for fieldname in ("date", "posting_date", "start_date", "from_date", "attendance_date"):
		if getattr(doc, fieldname, None):
			return getdate(getattr(doc, fieldname))

	# Timesheet fallback: derive from first log row if header date is missing
	if hasattr(doc, "time_logs") and doc.time_logs:
		for row in doc.time_logs:
			if getattr(row, "from_time", None):
				return getdate(str(row.from_time)[:10])
			if getattr(row, "to_time", None):
				return getdate(str(row.to_time)[:10])

	return getdate(nowdate())


@frappe.whitelist()
def enforce_payroll_cutoff(doc, method=None):
	# Restrict only new records; updates/cancellation of existing records remain allowed.
	if not doc.is_new():
		return

	cutoff_date = frappe.db.get_single_value("V HR Settings", "payroll_cut_off_date")
	if not cutoff_date:
		return

	cutoff_date = getdate(cutoff_date)
	today = getdate(nowdate())
	document_date = _resolve_document_date(doc)

	# Block new records once the system date has crossed the configured cut off date.
	if today > cutoff_date:
		frappe.throw(
			_(
				"Cannot create {0} because today's date {1} is after Payroll Cut Off Date {2}. "
				"Update V HR Settings to continue."
			).format(
				frappe.bold(doc.doctype),
				frappe.bold(today.strftime("%Y-%m-%d")),
				frappe.bold(cutoff_date.strftime("%Y-%m-%d")),
			)
		)

	# Also prevent forward-dated entries beyond cut off before crossing date.
	if document_date > cutoff_date:
		frappe.throw(
			_(
				"Cannot create {0} for date {1} because Payroll Cut Off Date is {2}. "
				"Update V HR Settings to continue."
			).format(
				frappe.bold(doc.doctype),
				frappe.bold(document_date.strftime("%Y-%m-%d")),
				frappe.bold(cutoff_date.strftime("%Y-%m-%d")),
			)
		)
