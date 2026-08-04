import frappe
from frappe import _
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry
from hr_vfg.hr_ventureforce_global.custom_events import create_salary_slips_for_employees
from hr_vfg.hr_ventureforce_global.payroll_accounting_fix import (
	clear_invalid_salary_slip_journal_links,
	validate_accrual_journal_entry,
)


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
