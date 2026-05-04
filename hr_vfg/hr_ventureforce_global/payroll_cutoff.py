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
	# Payroll cut-off enforcement is disabled. Keep the hook in place so it can be
	# re-enabled later without changing the event bindings again.
	return
