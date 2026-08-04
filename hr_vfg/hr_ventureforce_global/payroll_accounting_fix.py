import frappe
from frappe import _
from frappe.utils import flt

COMPANY = "SAH ENTERPRISE INC"

DEFAULT_EARNING_ACCOUNT = "Salary - SAH"
DEFAULT_DEDUCTION_ACCOUNT = "Payroll Deductions - SAH"
PAYROLL_DEDUCTIONS_ACCOUNT = "Payroll Deductions - SAH"

COMPONENT_ACCOUNT_MAP = {
	"Income Tax": "KEPZ TAX PAYABLE - SAH",
	"Advance Salary - Deduction": "Employee Advances - SAH",
	"Employee Advances - SAH": "Employee Advances - SAH",
	"Loan Amount": "Loan - SAH",
	"Other Deduction": PAYROLL_DEDUCTIONS_ACCOUNT,
	"Overtime Deduction": PAYROLL_DEDUCTIONS_ACCOUNT,
	"Absent Deduction": PAYROLL_DEDUCTIONS_ACCOUNT,
	"Manual Absent Deduction": PAYROLL_DEDUCTIONS_ACCOUNT,
	"Late Coming Hours 09": PAYROLL_DEDUCTIONS_ACCOUNT,
	"Early Going Hours 09": PAYROLL_DEDUCTIONS_ACCOUNT,
	"4 Lates Absent": PAYROLL_DEDUCTIONS_ACCOUNT,
	"Adjustment Plus": "Salary - SAH",
	"Arrear": "Salary - SAH",
	"Basic -Fix": "Salary - SAH",
	"Leave Encashment": "Salary - SAH",
}


def ensure_payroll_deductions_account(company=COMPANY):
	"""Create payroll deduction account so attendance/other deductions do not hit Salary expense."""
	if frappe.db.exists("Account", {"name": PAYROLL_DEDUCTIONS_ACCOUNT, "company": company}):
		return PAYROLL_DEDUCTIONS_ACCOUNT

	salary_account = frappe.db.get_value(
		"Account", {"name": DEFAULT_EARNING_ACCOUNT, "company": company}, ["parent_account"], as_dict=True
	)
	parent_account = (salary_account or {}).get("parent_account") or f"Administrative Expenses - {company.split()[0]}"

	if not frappe.db.exists("Account", parent_account):
		parent_account = frappe.db.get_value(
			"Account",
			{"company": company, "root_type": "Expense", "is_group": 1},
			"name",
		)

	account = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": "Payroll Deductions",
			"parent_account": parent_account,
			"company": company,
			"account_type": "Expense Account",
			"is_group": 0,
		}
	)
	account.insert(ignore_permissions=True)
	frappe.db.commit()
	return account.name


def get_default_account_for_component(component_name, component_type):
	if component_name in COMPONENT_ACCOUNT_MAP:
		return COMPONENT_ACCOUNT_MAP[component_name]

	if component_type == "Earning":
		return DEFAULT_EARNING_ACCOUNT

	if "advance" in component_name.lower() or "loan" in component_name.lower():
		return "Employee Advances - SAH"

	if component_type == "Deduction":
		return PAYROLL_DEDUCTIONS_ACCOUNT

	return DEFAULT_DEDUCTION_ACCOUNT


def fix_salary_component_accounts(company=COMPANY):
	ensure_payroll_deductions_account(company)
	fixed = []
	components = frappe.get_all("Salary Component", fields=["name", "type"])

	for component in components:
		account = get_default_account_for_component(component.name, component.type)
		existing = frappe.db.get_value(
			"Salary Component Account",
			{"parent": component.name, "company": company},
			["name", "account"],
			as_dict=True,
		)

		if existing and existing.account == account:
			continue

		if existing:
			frappe.db.set_value("Salary Component Account", existing.name, "account", account)
		else:
			doc = frappe.get_doc("Salary Component", component.name)
			doc.append("accounts", {"company": company, "account": account})
			doc.save(ignore_permissions=True)

		fixed.append({"component": component.name, "account": account})

	frappe.db.commit()
	return fixed


def clear_invalid_salary_slip_journal_links(payroll_entry_name):
	cleared = []
	salary_slips = frappe.get_all(
		"Salary Slip",
		filters={"payroll_entry": payroll_entry_name, "docstatus": 1},
		fields=["name", "journal_entry"],
	)

	for slip in salary_slips:
		if not slip.journal_entry:
			continue

		je_status = frappe.db.get_value("Journal Entry", slip.journal_entry, "docstatus")
		if je_status != 1:
			frappe.db.set_value("Salary Slip", slip.name, "journal_entry", None, update_modified=False)
			cleared.append(slip.name)

	if cleared:
		frappe.db.commit()

	return cleared


def validate_accrual_journal_entry(journal_entry_name, payroll_entry_name):
	je = frappe.get_doc("Journal Entry", journal_entry_name)
	summary = frappe._dict()
	for row in je.accounts:
		summary.setdefault(row.account, frappe._dict(debit=0, credit=0))
		summary[row.account].debit += flt(row.debit_in_account_currency)
		summary[row.account].credit += flt(row.credit_in_account_currency)

	totals = frappe.db.sql(
		"""
		SELECT
			COALESCE(SUM(gross_pay), 0) AS sum_gross_pay,
			COALESCE(SUM(total_deduction), 0) AS sum_total_deduction,
			COALESCE(SUM(net_pay), 0) AS sum_net_pay
		FROM `tabSalary Slip`
		WHERE payroll_entry = %s AND docstatus = 1
		""",
		payroll_entry_name,
		as_dict=True,
	)[0]

	payroll_payable = summary.get("Payroll Payable - SAH") or frappe._dict(debit=0, credit=0)
	salary_expense = summary.get("Salary - SAH") or frappe._dict(debit=0, credit=0)

	issues = []
	if flt(je.total_debit) != flt(je.total_credit):
		issues.append(_("Journal Entry is not balanced"))

	if flt(payroll_payable.debit) > 0:
		issues.append(_("Payroll Payable should not be debited in accrual Journal Entry"))

	if flt(salary_expense.debit) <= 0:
		issues.append(_("Salary expense is missing in accrual Journal Entry"))

	if flt(totals.sum_net_pay) and abs(flt(payroll_payable.credit) - flt(totals.sum_net_pay)) > 1:
		issues.append(
			_("Payroll Payable credit {0} does not match net pay {1}").format(
				payroll_payable.credit, totals.sum_net_pay
			)
		)

	return {
		"journal_entry": journal_entry_name,
		"balanced": not issues,
		"issues": issues,
		"summary": {account: dict(values) for account, values in summary.items()},
		"salary_totals": totals,
	}
