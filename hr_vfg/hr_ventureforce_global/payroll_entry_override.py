import frappe
from frappe import _
from frappe.utils import cint, flt, time_diff_in_hours, get_datetime, now_datetime
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry
from hr_vfg.hr_ventureforce_global.custom_events import create_salary_slips_for_employees
from hr_vfg.hr_ventureforce_global.payroll_accounting_fix import (
	clear_invalid_salary_slip_journal_links,
	validate_accrual_journal_entry,
)

PARTY_REQUIRED_ACCOUNT_TYPES = ("Receivable", "Payable")


def get_salary_slip_job_status(payroll_entry_name: str) -> dict:
	"""Return slip creation progress + background job state for Payroll Entry intro."""
	pe = frappe.db.get_value(
		"Payroll Entry",
		payroll_entry_name,
		[
			"name",
			"status",
			"docstatus",
			"salary_slips_created",
			"salary_slips_submitted",
			"number_of_employees",
			"error_message",
			"modified",
			"creation",
		],
		as_dict=True,
	)
	if not pe:
		return {"state": "missing"}

	employee_count = cint(pe.number_of_employees) or frappe.db.count(
		"Payroll Employee Detail", {"parent": payroll_entry_name}
	)
	slip_count = frappe.db.count(
		"Salary Slip", {"payroll_entry": payroll_entry_name, "docstatus": ["<", 2]}
	)
	waiting_hours = time_diff_in_hours(now_datetime(), get_datetime(pe.modified)) or 0

	job = _find_salary_slip_rq_job(payroll_entry_name)

	if cint(pe.salary_slips_created) and slip_count:
		state = "done"
		message = _("Salary slips created: {0} of {1}.").format(slip_count, employee_count)
		indicator = "green"
	elif pe.status == "Failed" or pe.error_message:
		state = "failed"
		message = _(
			"Salary slip creation <b>failed</b>. Check Error Message below, fix the issue, then retry Create Salary Slips."
		)
		indicator = "red"
	elif job and job.get("status") == "started":
		state = "running"
		message = _(
			"Salary slip creation job is <b>running now</b> ({0} of {1} slips so far). "
			"Please wait — refresh in a few minutes."
		).format(slip_count, employee_count)
		indicator = "blue"
	elif job and job.get("status") in ("queued", "deferred"):
		state = "queued"
		queue_info = ""
		if job.get("queue_position") is not None:
			queue_info = _(" Queue position: {0}.").format(job["queue_position"])
		message = _(
			"Salary slip creation is <b>queued</b> (not started yet) for {0} employees.{1} "
			"This is normal for large payrolls — slips will appear after the background worker runs. "
			"Do not panic if nothing shows for a while."
		).format(employee_count, queue_info)
		indicator = "orange"
	elif pe.docstatus == 1 and not cint(pe.salary_slips_created):
		# Submitted but no slips and no live job — likely stuck / lost from queue
		state = "stuck"
		message = _(
			"Payroll Entry is submitted but salary slips are <b>not created yet</b> "
			"({0} of {1}). No active background job found. "
			"Waiting for about {2} hour(s). Use <b>Create Salary Slips</b> to re-queue, "
			"or ask admin to check background workers."
		).format(slip_count, employee_count, flt(waiting_hours, 1))
		indicator = "red" if waiting_hours >= 1 else "orange"
	elif pe.status == "Queued":
		state = "queued"
		message = _(
			"Salary slip creation is <b>queued</b>. Background worker will create slips soon. "
			"Refresh this page to update progress."
		)
		indicator = "orange"
	else:
		state = "idle"
		message = ""
		indicator = "blue"

	return {
		"state": state,
		"message": message,
		"indicator": indicator,
		"employee_count": employee_count,
		"slip_count": slip_count,
		"salary_slips_created": cint(pe.salary_slips_created),
		"status": pe.status,
		"waiting_hours": flt(waiting_hours, 2),
		"job": job,
	}


def _find_salary_slip_rq_job(payroll_entry_name: str) -> dict | None:
	"""Look for queued/started RQ jobs for this payroll entry's slip creation."""
	try:
		from rq.registry import StartedJobRegistry, DeferredJobRegistry
		from frappe.utils.background_jobs import get_queues
	except Exception:
		return None

	job_name = f"create_salary_slips:{payroll_entry_name}"

	def _match(job):
		if not job:
			return False
		try:
			if getattr(job, "description", None) and job_name in str(job.description):
				return True
			fn = str(getattr(job, "func_name", "") or "")
			if "create_salary_slips" not in fn:
				return False
			kwargs = job.kwargs or {}
			args = kwargs.get("args") or {}
			pe = args.get("payroll_entry") if hasattr(args, "get") else None
			return pe == payroll_entry_name
		except Exception:
			return False

	# Started
	for q in get_queues():
		try:
			reg = StartedJobRegistry(queue=q)
			for jid in reg.get_job_ids():
				job = q.fetch_job(jid)
				if _match(job):
					return {"status": "started", "job_id": jid, "queue": q.name}
		except Exception:
			continue

	# Queued / deferred
	for q in get_queues():
		try:
			# position in queue
			for idx, job in enumerate(q.jobs):
				if _match(job):
					return {
						"status": "queued",
						"job_id": job.id,
						"queue": q.name,
						"queue_position": idx + 1,
					}
			reg = DeferredJobRegistry(queue=q)
			for jid in reg.get_job_ids():
				job = q.fetch_job(jid)
				if _match(job):
					return {"status": "deferred", "job_id": jid, "queue": q.name}
		except Exception:
			continue

	return None


class CustomPayrollEntry(PayrollEntry):
	@frappe.whitelist()
	def create_salary_slips(self):
		"""Creates salary slip for selected employees if already not created."""
		self.check_permission("write")
		employees = [emp.employee for emp in self.employees]
		if employees:
			args = frappe._dict(
				{
					"salary_slip_based_on_timesheet": self.salary_slip_based_on_timesheet,
					"payroll_frequency": self.payroll_frequency,
					"start_date": self.start_date,
					"end_date": self.end_date,
					"company": self.company,
					"posting_date": self.posting_date,
					# Field removed in HRMS v16 — keep via getattr for older sites
					"deduct_tax_for_unclaimed_employee_benefits": getattr(
						self, "deduct_tax_for_unclaimed_employee_benefits", 0
					),
					"deduct_tax_for_unsubmitted_tax_exemption_proof": self.deduct_tax_for_unsubmitted_tax_exemption_proof,
					"payroll_entry": self.name,
					"exchange_rate": self.exchange_rate,
					"currency": self.currency,
				}
			)
			if len(employees) > 30 or frappe.flags.enqueue_payroll_entry:
				self.db_set({"status": "Queued", "error_message": ""})
				frappe.enqueue(
					create_salary_slips_for_employees,
					queue="long",
					timeout=3000,
					employees=employees,
					args=args,
					publish_progress=False,
					job_name=f"create_salary_slips:{self.name}",
				)
				frappe.msgprint(
					_(
						"Salary Slip creation is <b>queued</b> for {0} employees. "
						"This can take several minutes — do not panic if slips are not visible yet. "
						"Refresh this page to see progress."
					).format(len(employees)),
					title=_("Salary Slips Queued"),
					indicator="blue",
				)
			else:
				create_salary_slips_for_employees(employees, args, publish_progress=False)
				self.reload()

	@frappe.whitelist()
	def get_salary_slip_creation_status(self):
		"""Queue / progress status for salary slip creation (shown on form intro)."""
		return get_salary_slip_job_status(self.name)

	@frappe.whitelist()
	def get_accrual_jv_status(self):
		salary_slips = frappe.get_all(
			"Salary Slip",
			filters={"payroll_entry": self.name, "docstatus": 1},
			fields=["name", "journal_entry"],
		)
		journal_entries = {slip.journal_entry for slip in salary_slips if slip.journal_entry}
		active = []
		cancelled = []

		for journal_entry in journal_entries:
			status = frappe.db.get_value("Journal Entry", journal_entry, ["name", "docstatus"], as_dict=True)
			if not status:
				continue
			if status.docstatus == 1:
				active.append(status.name)
			elif status.docstatus == 2:
				cancelled.append(status.name)

		return {
			"salary_slip_count": len(salary_slips),
			"active_journal_entries": active,
			"cancelled_journal_entries": cancelled,
			"needs_accrual_jv": not active,
		}

	def _account_requires_party(self, account: str) -> bool:
		account_type = frappe.get_cached_value("Account", account, "account_type")
		return account_type in PARTY_REQUIRED_ACCOUNT_TYPES

	def _get_employee_amounts_for_party_account(self, account: str, component_type: str):
		"""Split Receivable/Payable component amounts by employee + cost center."""
		salary_components = self.get_salary_components(component_type) or []
		totals = {}

		for item in salary_components:
			component_account = self.get_salary_component_account(item.salary_component)
			if component_account != account:
				continue

			# Skip rows already handled as linked Employee Advance deductions
			if component_type == "deductions" and self.get_advance_deduction(component_type, item):
				continue

			employee_cost_centers = self.get_payroll_cost_centers_for_employee(
				item.employee, item.salary_structure
			)
			for cost_center, percentage in employee_cost_centers.items():
				amount = flt(item.amount) * percentage / 100
				if not amount:
					continue
				key = (item.employee, cost_center or self.cost_center)
				totals[key] = totals.get(key, 0) + amount

		return totals

	def get_payable_amount_for_earnings_and_deductions(
		self,
		accounts,
		earnings,
		deductions,
		currencies,
		company_currency,
		accounting_dimensions,
		precision,
		payable_amount,
		employee_wise_accounting_enabled,
	):
		"""Post party-required component accounts employee-wise.

		Standard HRMS aggregates component accounts. That breaks when a deduction
		like Employee Advances - SAH uses a Receivable account without Additional
		Salary → Employee Advance linkage (no party on the JV row).
		"""
		for acc_cc, amount in earnings.items():
			account, cost_center = acc_cc[0], acc_cc[1] or self.cost_center
			if self._account_requires_party(account):
				employee_amounts = self._get_employee_amounts_for_party_account(account, "earnings")
				for (employee, emp_cc), emp_amount in employee_amounts.items():
					payable_amount = self.get_accounting_entries_and_payable_amount(
						account,
						emp_cc or cost_center,
						emp_amount,
						currencies,
						company_currency,
						payable_amount,
						accounting_dimensions,
						precision,
						entry_type="debit",
						party=employee,
						accounts=accounts,
					)
			else:
				payable_amount = self.get_accounting_entries_and_payable_amount(
					account,
					cost_center,
					amount,
					currencies,
					company_currency,
					payable_amount,
					accounting_dimensions,
					precision,
					entry_type="debit",
					accounts=accounts,
				)

		for acc_cc, amount in deductions.items():
			account, cost_center = acc_cc[0], acc_cc[1] or self.cost_center
			if self._account_requires_party(account):
				employee_amounts = self._get_employee_amounts_for_party_account(account, "deductions")
				for (employee, emp_cc), emp_amount in employee_amounts.items():
					payable_amount = self.get_accounting_entries_and_payable_amount(
						account,
						emp_cc or cost_center,
						emp_amount,
						currencies,
						company_currency,
						payable_amount,
						accounting_dimensions,
						precision,
						entry_type="credit",
						party=employee,
						accounts=accounts,
					)
			else:
				payable_amount = self.get_accounting_entries_and_payable_amount(
					account,
					cost_center,
					amount,
					currencies,
					company_currency,
					payable_amount,
					accounting_dimensions,
					precision,
					entry_type="credit",
					accounts=accounts,
				)

		return payable_amount

	def make_accrual_jv_entry(self, submitted_salary_slips):
		super().make_accrual_jv_entry(submitted_salary_slips)

		for slip in submitted_salary_slips:
			journal_entry_name = frappe.db.get_value("Salary Slip", slip.name, "journal_entry")
			if journal_entry_name and frappe.db.get_value("Journal Entry", journal_entry_name, "docstatus") == 1:
				return frappe.get_doc("Journal Entry", journal_entry_name)

		return None

	@frappe.whitelist()
	def make_accrual_journal_entry(self):
		"""Create or recreate payroll accrual Journal Entry for submitted salary slips."""
		self.check_permission("write")

		if not self.salary_slips_submitted:
			frappe.throw(_("Submit Salary Slips before creating the accrual Journal Entry."))

		submitted_names = frappe.get_all(
			"Salary Slip",
			filters={"payroll_entry": self.name, "docstatus": 1},
			pluck="name",
		)
		if not submitted_names:
			frappe.throw(_("No submitted Salary Slips found for this Payroll Entry."))

		status = self.get_accrual_jv_status()
		if status.get("active_journal_entries"):
			journal_entry_name = status["active_journal_entries"][0]
			validation = validate_accrual_journal_entry(journal_entry_name, self.name)
			return {"journal_entry": journal_entry_name, "validation": validation, "already_exists": True}

		cleared = clear_invalid_salary_slip_journal_links(self.name)
		submitted_docs = [frappe.get_doc("Salary Slip", name) for name in submitted_names]
		journal_entry = self.make_accrual_jv_entry(submitted_docs)

		if not journal_entry:
			slips_without_je = len(self.get_sal_slip_list(ss_status=1, as_dict=True))
			frappe.throw(
				_(
					"Could not create accrual Journal Entry. Salary slips ready for accrual: {0}. "
					"Cleared invalid journal links from {1} salary slip(s). "
					"Please verify Salary Component accounts are set for company {2}."
				).format(slips_without_je, len(cleared), self.company)
			)

		frappe.db.commit()

		validation = validate_accrual_journal_entry(journal_entry.name, self.name)
		if not validation["balanced"]:
			frappe.msgprint(
				_("Accrual Journal Entry {0} was created, but please review it:<br>{1}").format(
					journal_entry.name,
					"<br>".join(validation["issues"]),
				),
				indicator="orange",
				title=_("Review Journal Entry"),
			)
		else:
			frappe.msgprint(
				_("Accrual Journal Entry {0} created successfully.").format(journal_entry.name),
				indicator="green",
				title=_("Success"),
			)

		return {"journal_entry": journal_entry.name, "validation": validation}
