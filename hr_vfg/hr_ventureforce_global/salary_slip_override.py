# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import datetime
import math
from operator import index

import frappe
from frappe import _, msgprint
from frappe.model.naming import make_autoname
from frappe.utils import (
	add_days,
	cint,
	cstr,
	date_diff,
	flt,
	formatdate,
	get_first_day,
	get_last_day,
	getdate,
	money_in_words,
	rounded,
)
import calendar
from frappe.utils.background_jobs import enqueue
from six import iteritems

from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from erpnext.setup.doctype.employee.employee import (
    InactiveEmployeeStatusError
)

# from hrms.hr.doctype.employee.employee import (
# 	InactiveEmployeeStatusError,
# 	get_holiday_list_for_employee,
# )

import erpnext
from erpnext.accounts.utils import get_fiscal_year
from hrms.hr.utils import get_holiday_dates_for_employee, validate_active_employee
# from erpnext.loan_management.doctype.loan_repayment.loan_repayment import (
# 	calculate_amounts,
# 	create_repayment_entry,
# )
from hrms.payroll.doctype.additional_salary.additional_salary import get_additional_salaries
from hrms.payroll.doctype.payroll_entry.payroll_entry import get_start_end_dates
from erpnext.utilities.transaction_base import TransactionBase
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip


class CustomSalarySlip(SalarySlip):
    def get_advance_deduction_component(self):
        # Get the latest salary structure assignment for the employee as of the end date
        assignment = frappe.get_all(
            "Salary Structure Assignment",
            filters={
                "employee": self.employee,
                "from_date": ["<=", self.end_date],
                "docstatus": 1,
            },
            fields=["salary_structure"],
            order_by="from_date desc",
            limit=1,
        )
        if not assignment:
            return None

        salary_structure = assignment[0].salary_structure
        structure_doc = frappe.get_doc("Salary Structure", salary_structure)
        # Find deduction component with 'advance' in the name
        for row in structure_doc.deductions:
            if "advance" in row.salary_component.lower():
                return row.salary_component
        return None

    def _get_outstanding_salary_advances(self):
        """All repay-from-salary advances still open as of this slip end date.

        Older code limited posting_date to the current payroll month only, so prior
        unpaid advances were never deducted again and never closed.
        """
        return frappe.get_all(
            "Employee Advance",
            filters={
                "employee": self.employee,
                "repay_unclaimed_amount_from_salary": 1,
                "docstatus": 1,
                "status": ["in", ["Paid", "Unpaid"]],
                "posting_date": ["<=", self.end_date],
            },
            fields=[
                "name",
                "paid_amount",
                "claimed_amount",
                "return_amount",
                "advance_amount",
                "advance_account",
                "posting_date",
            ],
            order_by="posting_date asc, creation asc",
        )

    def _advance_unclaimed_amount(self, adv) -> float:
        paid = min(flt(adv.paid_amount), flt(adv.advance_amount) or flt(adv.paid_amount))
        return flt(paid) - flt(adv.claimed_amount) - flt(adv.return_amount)

    def _ensure_advance_additional_salary(self, adv_name: str, amount: float, component: str):
        """Create/submit Additional Salary linked to Employee Advance (updates return_amount)."""
        existing = frappe.get_all(
            "Additional Salary",
            filters={
                "employee": self.employee,
                "ref_doctype": "Employee Advance",
                "ref_docname": adv_name,
                "docstatus": 1,
                "payroll_date": ["between", [self.start_date, self.end_date]],
            },
            fields=["name", "amount"],
            limit=1,
        )
        if existing:
            return existing[0].name

        if amount <= 0:
            return None

        additional_salary = frappe.new_doc("Additional Salary")
        additional_salary.employee = self.employee
        additional_salary.company = self.company
        additional_salary.payroll_date = self.end_date
        additional_salary.salary_component = component
        additional_salary.type = "Deduction"
        additional_salary.currency = self.currency
        additional_salary.amount = amount
        additional_salary.overwrite_salary_structure_amount = 0
        additional_salary.ref_doctype = "Employee Advance"
        additional_salary.ref_docname = adv_name
        additional_salary.insert(ignore_permissions=True)
        additional_salary.submit()
        return additional_salary.name

    def add_employee_advance_deductions(self):
        """Deduct outstanding Employee Advances from salary.

        - Includes advances from previous months (not only current period)
        - Uses Additional Salary so Employee Advance.return_amount is updated
        - Caps total advance deduction so net pay does not go negative
        """
        advances = self._get_outstanding_salary_advances()
        if not advances:
            return

        deduction_component = self.get_advance_deduction_component()
        if not deduction_component:
            frappe.throw(
                _("No 'Advance' deduction component found in the assigned Salary Structure for this employee.")
            )

        # Room for advance recovery after other non-advance deductions
        non_advance_deductions = sum(
            flt(d.amount)
            for d in self.get("deductions", [])
            if "advance" not in (d.salary_component or "").lower()
        )
        available_for_advance = max(flt(self.gross_pay) - flt(non_advance_deductions), 0)
        if available_for_advance <= 0:
            return

        # Drop only unlinked advance rows; keep Additional Salary rows and rebuild below
        for i in reversed(range(len(self.get("deductions", [])))):
            row = self.deductions[i]
            if "advance" in (row.salary_component or "").lower() and not row.additional_salary:
                self.remove(row)

        # Remove current-period advance AS rows from slip; will re-add after ensuring AS docs
        for i in reversed(range(len(self.get("deductions", [])))):
            row = self.deductions[i]
            if "advance" in (row.salary_component or "").lower():
                self.remove(row)

        remaining_room = available_for_advance
        for adv in advances:
            if remaining_room <= 0:
                break

            existing = frappe.get_all(
                "Additional Salary",
                filters={
                    "employee": self.employee,
                    "ref_doctype": "Employee Advance",
                    "ref_docname": adv.name,
                    "docstatus": 1,
                    "payroll_date": ["between", [self.start_date, self.end_date]],
                },
                fields=["name", "amount"],
                limit=1,
            )

            if existing:
                # AS submit already updates return_amount — still must keep the slip line
                as_name = existing[0].name
                post_amount = min(flt(existing[0].amount), remaining_room)
            else:
                unclaimed = self._advance_unclaimed_amount(adv)
                if unclaimed <= 0:
                    continue
                post_amount = min(unclaimed, remaining_room)
                as_name = self._ensure_advance_additional_salary(
                    adv.name, post_amount, deduction_component
                )
                if not as_name:
                    continue

            if post_amount <= 0 or not as_name:
                continue

            self.append(
                "deductions",
                {
                    "salary_component": deduction_component,
                    "amount": post_amount,
                    "additional_salary": as_name,
                },
            )
            remaining_room = max(remaining_room - post_amount, 0)

    def set_employee_grade(self):
        """Copy Employee Grade from Employee.custom_employee_grade onto the slip.

        Standard Employee.grade is hidden/unused here; the live grade is
        custom_employee_grade. Without this, list filters on Grade never match.
        """
        if not self.employee or not self.meta.has_field("custom_grade"):
            return
        emp_grade = frappe.db.get_value(
            "Employee", self.employee, "custom_employee_grade"
        )
        if emp_grade and self.custom_grade != emp_grade:
            self.custom_grade = emp_grade
        elif not emp_grade and self.custom_grade:
            # Keep existing value if employee grade was cleared after slip creation
            pass

    def validate(self):
        self.set_employee_grade()
        super().validate()
        self.add_employee_advance_deductions()
        # Advances are appended after structure calc — refresh totals
        self.set_precision_for_component_amounts()
        self.set_net_pay()

	# def get_taxable_earnings_for_prev_period(self, payroll_period,start_date, end_date, allow_tax_exemption=False):
	# 	payroll_period = get_payroll_period(self.start_date, self.end_date, self.company)
	# 	prev = frappe.db.sql("""select previous_salary_earned from `tabPrevious Salary Detail` where employee=%s and payroll_period=%s""",
	# 		(self.employee,payroll_period.name))
		
	# 	prev_earned = flt(prev[0][0]) if prev else 0	
	# 	taxable_earnings = frappe.db.sql("""
	# 		select sum(sd.amount)
	# 		from
	# 			`tabSalary Detail` sd join `tabSalary Slip` ss on sd.parent=ss.name
	# 		where
	# 			sd.parentfield='earnings'
	# 			and sd.is_tax_applicable=1
	# 			and is_flexible_benefit=0
	# 			and ss.docstatus=1
	# 			and ss.employee=%(employee)s
	# 			and ss.start_date between %(from_date)s and %(to_date)s
	# 			and ss.end_date between %(from_date)s and %(to_date)s
	# 		""", {
	# 			"employee": self.employee,
	# 			"from_date": start_date,
	# 			"to_date": end_date
	# 		})
	# 	taxable_earnings = flt(taxable_earnings[0][0]) if taxable_earnings else 0

	# 	exempted_amount = 0
	# 	if allow_tax_exemption:
	# 		exempted_amount = frappe.db.sql("""
	# 			select sum(sd.amount)
	# 			from
	# 				`tabSalary Detail` sd join `tabSalary Slip` ss on sd.parent=ss.name
	# 			where
	# 				sd.parentfield='deductions'
	# 				and sd.exempted_from_income_tax=1
	# 				and is_flexible_benefit=0
	# 				and ss.docstatus=1
	# 				and ss.employee=%(employee)s
	# 				and ss.start_date between %(from_date)s and %(to_date)s
	# 				and ss.end_date between %(from_date)s and %(to_date)s
	# 			""", {
	# 				"employee": self.employee,
	# 				"from_date": start_date,
	# 				"to_date": end_date
	# 			})
	# 		exempted_amount = flt(exempted_amount[0][0]) if exempted_amount else 0

		
	# 	frappe.msgprint(str(prev_earned))
	# 	return (taxable_earnings + prev_earned) - exempted_amount
	
	# def get_tax_paid_in_period(self, start_date, end_date, tax_component):
	# 			payroll_period = get_payroll_period(self.start_date, self.end_date, self.company)
	# 			prev = frappe.db.sql("""select previous_tax_paid from `tabPrevious Salary Detail` where employee=%s and payroll_period=%s""",
	# 				(self.employee,payroll_period.name))
	# 			prev_paid = flt(prev[0][0]) if prev else 0
	# 			# find total_tax_paid, tax paid for benefit, additional_salary
	# 			total_tax_paid = flt(frappe.db.sql("""
	# 				select
	# 					sum(sd.amount)
	# 				from
	# 					`tabSalary Detail` sd join `tabSalary Slip` ss on sd.parent=ss.name
	# 				where
	# 					sd.parentfield='deductions'
	# 					and sd.salary_component=%(salary_component)s
	# 					and sd.variable_based_on_taxable_salary=1
	# 					and ss.docstatus=1
	# 					and ss.employee=%(employee)s
	# 					and ss.start_date between %(from_date)s and %(to_date)s
	# 					and ss.end_date between %(from_date)s and %(to_date)s
	# 			""", {
	# 				"salary_component": tax_component,
	# 				"employee": self.employee,
	# 				"from_date": start_date,
	# 				"to_date": end_date
	# 			})[0][0])

	# 			return total_tax_paid + prev_paid

def add_leaves(doc, method):
			
			rec = frappe.db.sql("""select name from `tabLeave Application` where status="Approved" and  from_date>=%s and to_date<=%s 
				                             and employee=%s and custom_late_absent_adjusted_as_a_leave=1 and docstatus=1 """,
				                      (getdate(doc.get("start_date")),getdate(doc.get("end_date")),doc.employee), as_dict=True)
			
			adj_list = []
			for r in rec:
				adj_list.append(r.name)

			doc.late_adjustments = len(adj_list)
			doc.absents_adjustments = len(frappe.db.get_all("Attendance", 
						{"attendance_date":["between",[doc.start_date,doc.end_date]],"status":"On Leave","docstatus":1,
							"employee":doc.employee,"leave_application":["not in",adj_list]}))
			doc.half_days_adjustments =  len(frappe.db.get_all("Attendance", 
						{"attendance_date":["between",[doc.start_date,doc.end_date]],"status":"Half Day","docstatus":1,
							"employee":doc.employee,"leave_application":["not in",adj_list]}))
			doc.annual_leave_ =  len(frappe.db.get_all("Attendance", 
						{"attendance_date":["between",[doc.start_date,doc.end_date]],"status":"On Leave","docstatus":1,
							"employee":doc.employee,"leave_type":"Annual Leave"})) + (len(frappe.db.get_all("Attendance", 
						{"attendance_date":["between",[doc.start_date,doc.end_date]],"status":"Half Day","docstatus":1,
							"employee":doc.employee,"leave_type":"Annual Leave"}))/2)
			doc.sick_leave = len(frappe.db.get_all("Attendance", 
						{"attendance_date":["between",[doc.start_date,doc.end_date]],"status":"On Leave","docstatus":1,
							"employee":doc.employee,"leave_type":"Sick Leave"})) + (len(frappe.db.get_all("Attendance", 
						{"attendance_date":["between",[doc.start_date,doc.end_date]],"status":"Half Day","docstatus":1,
							"employee":doc.employee,"leave_type":"Sick Leave"}))/2)
			doc.emergency_leave = len(frappe.db.get_all("Attendance", 
						{"attendance_date":["between",[doc.start_date,doc.end_date]],"status":"On Leave","docstatus":1,
							"employee":doc.employee,"leave_type":"Emergency Leave"})) + (len(frappe.db.get_all("Attendance", 
						{"attendance_date":["between",[doc.start_date,doc.end_date]],"status":"Half Day","docstatus":1,
							"employee":doc.employee,"leave_type":"Emergency Leave"}))/2)
			doc.casual_leave = len(frappe.db.get_all("Attendance", 
						{"attendance_date":["between",[doc.start_date,doc.end_date]],"status":"On Leave","docstatus":1,
							"employee":doc.employee,"leave_type":"Casual Leave"})) + (len(frappe.db.get_all("Attendance", 
						{"attendance_date":["between",[doc.start_date,doc.end_date]],"status":"Half Day","docstatus":1,
							"employee":doc.employee,"leave_type":"Casual Leave"}))/2)
			
		