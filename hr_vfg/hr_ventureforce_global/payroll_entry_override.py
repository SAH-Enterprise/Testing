import frappe
from frappe import _
from frappe.utils import flt
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry
from hr_vfg.hr_ventureforce_global.custom_events import create_salary_slips_for_employees
from hr_vfg.hr_ventureforce_global.payroll_accounting_fix import (
	clear_invalid_salary_slip_journal_links,
	validate_accrual_journal_entry,
)

PARTY_REQUIRED_ACCOUNT_TYPES = ("Receivable", "Payable")


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
			if len(employees) > 30:
				frappe.enqueue(create_salary_slips_for_employees, timeout=600, employees=employees, args=args)
			else:
				create_salary_slips_for_employees(employees, args, publish_progress=False)
				self.reload()

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
