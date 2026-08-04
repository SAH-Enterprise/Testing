import json

import frappe
from frappe import _
from frappe.desk.reportview import get_filters_cond, get_match_cond
from frappe.model.document import Document
from frappe.utils import (
	DATE_FORMAT,
	add_days,
	add_to_date,
	cint,
	comma_and,
	date_diff,
	flt,
	get_link_to_form,
	getdate,
)
from hrms.payroll.doctype.payroll_entry.payroll_entry import get_existing_salary_slips


def create_missing_additional_salaries_for_advances(employee, start_date, end_date):
    """
    Create additional salary records for employee advances that are missing them.
    """
    missing_advances = check_employee_advances_for_salary_deduction(employee, start_date, end_date)
    created_additional_salaries = []
    
    for advance_info in missing_advances:
        advance_name = advance_info["advance_name"]
        unclaimed_amount = advance_info["unclaimed_amount"]
        
        # Get the employee advance document
        advance_doc = frappe.get_doc("Employee Advance", advance_name)
        
        # Create additional salary using the standard method
        from hrms.hr.doctype.employee_advance.employee_advance import create_return_through_additional_salary
        
        additional_salary = create_return_through_additional_salary(advance_doc)
        
        # Set the payroll date to the end date of the payroll period
        additional_salary.payroll_date = end_date
        
        # Set the amount to the unclaimed amount
        additional_salary.amount = unclaimed_amount
        additional_salary.salary_component = "Advance Salary - Deduction"
        additional_salary.type = "Deduction"
        
        # Insert and submit the additional salary
        additional_salary.insert()
        additional_salary.submit()
        
        created_additional_salaries.append({
            "advance_name": advance_name,
            "additional_salary_name": additional_salary.name,
            "amount": unclaimed_amount
        })
    
    return created_additional_salaries


@frappe.whitelist()
def create_missing_advance_deductions(payroll_entry_name):
    """
    Create missing additional salary records for employee advances in a payroll entry.
    """
    payroll_entry = frappe.get_doc("Payroll Entry", payroll_entry_name)
    created_records = []
    
    for employee_row in payroll_entry.employees:
        employee = employee_row.employee
        created = create_missing_additional_salaries_for_advances(
            employee, payroll_entry.start_date, payroll_entry.end_date
        )
        created_records.extend(created)
    
    if created_records:
        advance_names = [record["advance_name"] for record in created_records]
        additional_salary_names = [record["additional_salary_name"] for record in created_records]
        total_amount = sum(record["amount"] for record in created_records)
        
        frappe.msgprint(
            _(
                "Created {0} additional salary records for employee advances: {1}. "
                "Total amount: {2}. Additional Salary records: {3}"
            ).format(
                len(created_records),
                frappe.bold(", ".join(advance_names)),
                frappe.bold(frappe.utils.fmt_money(total_amount)),
                frappe.bold(", ".join(additional_salary_names))
            ),
            title=_("Additional Salary Records Created"),
            indicator="green",
        )
    else:
        frappe.msgprint(
            _("No missing employee advance deductions found."),
            title=_("No Action Required"),
            indicator="blue",
        )
    
    return {"created_records": created_records}


def check_employee_advances_for_salary_deduction(employee, start_date, end_date):
    """
    Check if there are any employee advances that should be deducted from salary
    but are missing additional salary records.
    """
    advances = frappe.get_all(
        "Employee Advance",
        filters={
            "employee": employee,
            "repay_unclaimed_amount_from_salary": 1,
            "docstatus": 1,
            "status": ["in", ["Paid", "Unpaid"]],
            # Only include advances that were posted within the salary slip period
            "posting_date": ["between", [start_date, end_date]]
        },
        fields=["name", "advance_amount", "paid_amount", "claimed_amount", "return_amount", "posting_date"]
    )
    
    missing_additional_salaries = []
    
    for advance in advances:
        unclaimed_amount = min(flt(advance.paid_amount), flt(advance.advance_amount) or flt(advance.paid_amount))
        unclaimed_amount = unclaimed_amount - flt(advance.claimed_amount) - flt(advance.return_amount)
        
        if unclaimed_amount > 0:
            # Check if there's an additional salary for this advance in the current payroll period
            additional_salary = frappe.get_all(
                "Additional Salary",
                filters={
                    "employee": employee,
                    "ref_doctype": "Employee Advance",
                    "ref_docname": advance.name,
                    "docstatus": 1,
                    "payroll_date": ["between", [start_date, end_date]]
                },
                fields=["name", "amount"]
            )
            
            if not additional_salary:
                missing_additional_salaries.append({
                    "advance_name": advance.name,
                    "unclaimed_amount": unclaimed_amount,
                    "posting_date": advance.posting_date
                })
    
    return missing_additional_salaries


@frappe.whitelist()
def get_employee_attendance_status(payroll_entry_name):
    """
    For each row in the 'employees' child table of this Payroll Entry,
    attempt to find an Employee Attendance for that employee for the
    payroll's month/year. If found AND present_days > 1, mark:
        - child_row.custom_attendance = True
        - child_row.employee_attendance_name = attendance_doc.name
    Otherwise, clear those fields.
    """
    # 1. Load the parent document
    pe = frappe.get_doc("Payroll Entry", payroll_entry_name)

    # 2. Determine month and year from the Payroll Entry's end_date
    try:
        end_date = getdate(pe.end_date)
    except Exception:
        frappe.throw(_("Cannot parse end_date on Payroll Entry {0}").format(pe.name))

    month_index = end_date.month  # 1–12
    year = end_date.year
    # Convert numeric month to full month name:
    months = ["January","February","March","April","May","June","July","August","September","October","November","December"]
    month_str = months[month_index - 1]
    

    # 3. Loop through each child row in pe.employees
    for row in pe.employees:
        emp = row.employee
        found = False
        

        # 3a. Try to fetch exactly one Employee Attendance record for this employee/month/year
        attendance_list = frappe.get_all(
            "Employee Attendance",
            filters={
                "employee": emp,
                "month": month_str,
                "year": year,
            },
            fields=["name", "present_days"],
            limit=1
        )
        

        if attendance_list:
            att = attendance_list[0]
            # 3b. If present_days > 1, set the flags
            # if att.get("present_days") and flt(att.get("present_days")) > 1:
            if flt(att.get("present_days")) > 1:
                row.custom_attendance = 1
                row.custom_employee_attendance = att.get("name")
                # frappe.log_error= att.get('name')
                found = True
            else:
                row.custom_attendance = 0
                row.custom_employee_attendance = ""

        # 3c. If not found or present_days ≤ 1 → clear those fields
        if not found:
            row.custom_attendance = 0
            row.custom_employee_attendance = ""

    # 4. Save the parent doc (this will persist child‐row changes)
    pe.flags.ignore_mandatory = True   # if any other mandatory child fields exist
    pe.save(ignore_permissions=True)

    return {"status": "ok"}

@frappe.whitelist()
def create_salary_slips(self):
		"""
		Creates salary slip for selected employees if already not created
		"""
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
				# since this method is called via frm.call this doc needs to be updated manually
				self.reload()
				
def _get_payroll_error_message(error):
    message_log = frappe.message_log.pop() if frappe.message_log else str(error)

    try:
        if isinstance(message_log, str):
            return json.loads(message_log).get("message") or str(error)

        return message_log.get("message") or str(error)
    except Exception:
        return str(message_log or error)


def _mark_payroll_entry_failed(args, error):
    payroll_entry_name = args.get("payroll_entry")
    if not payroll_entry_name:
        return

    error_log = frappe.log_error(
        title=_("Salary Slip creation failed for Payroll Entry {0}").format(payroll_entry_name),
        reference_doctype="Payroll Entry",
        reference_name=payroll_entry_name,
    )

    error_message = _get_payroll_error_message(error)
    if error_log:
        error_message += "\n" + _("Check Error Log {0} for more details.").format(
            get_link_to_form("Error Log", error_log.name)
        )

    payroll_entry = frappe.get_doc("Payroll Entry", payroll_entry_name)
    payroll_entry.db_set({"error_message": error_message, "status": "Failed"})
    payroll_entry.notify_update()


def _create_salary_slips_for_employees(employees, args, publish_progress=True):
        salary_slips_exists_for = get_existing_salary_slips(employees, args)
        count = 0
        salary_slips_not_created = []
        missing_advances = []
        
        for emp in employees:
            if emp not in salary_slips_exists_for:
                # Ensure we're using the correct date format
                end_date = getdate(args.get("end_date"))
                e_month = end_date.month
                year = end_date.year
                month_str = ["January", "February", "March", "April","May","June","July","August","September","October","November","December"][e_month-1]
                
                # Debug: Print the dates to see what's happening
                frappe.log_error(f"Payroll dates - Start: {args.get('start_date')}, End: {args.get('end_date')}, Month: {month_str}, Year: {year}", "PAYROLL_DEBUG")
                
                try:
                    employee_att = frappe.get_all("Employee Attendance",
                    filters={"month":month_str,"employee": emp,"year":year},fields=["*"])[0]
                    
                    args.update({
                    "select_month": month_str,
                    "employee_attendance": employee_att.name,
                    # "lates": employee_att.total_lates,
                    # "early_goings": employee_att.early_goings,
                    # "late_sitting_hours": employee_att.late_sitting_hours,
                    # "present_day": employee_att.present_days,
                    # "over_times": employee_att.over_time,
                    # "short_hours": employee_att.short_hours,
                    # "absents": employee_att.total_absents,
                    # "half_days": employee_att.total_half_days,
                    # "late_adjusted_absents":int(employee_att.total_lates)/3,
                    
                    })

                except:
                    frappe.error_log(frappe.get_traceback(),"PAYROLL")
                
                # Check for missing employee advance deductions
                missing_advances_for_emp = check_employee_advances_for_salary_deduction(
                    emp, args.get("start_date"), args.get("end_date")
                )
                if missing_advances_for_emp:
                    missing_advances.extend(missing_advances_for_emp)
                
                args.update({"doctype": "Salary Slip", "employee": emp})
                ss = frappe.get_doc(args)
                
                # Add custom leave calculations
                add_leaves(ss)
                
                # Calculate salary components including additional salaries (employee advances)
                if ss.salary_structure:
                    ss.calculate_component_amounts("earnings")
                    ss.calculate_component_amounts("deductions")
                
                ss.insert()
                
                # Calculate net pay to ensure all components are properly calculated
                ss.calculate_net_pay()
                ss.save()
                
                count += 1
                if publish_progress:
                    frappe.publish_progress(
                        count * 100 / len(set(employees) - set(salary_slips_exists_for)),
                        title=_("Creating Salary Slips..."),
                    )

            else:
                salary_slips_not_created.append(emp)

        payroll_entry = frappe.get_doc("Payroll Entry", args.payroll_entry)
        payroll_entry.db_set("salary_slips_created", 1)
        payroll_entry.notify_update()

        # Show warning about missing employee advance deductions
        if missing_advances:
            advance_names = [adv["advance_name"] for adv in missing_advances]
            total_amount = sum(adv["unclaimed_amount"] for adv in missing_advances)
            frappe.msgprint(
                _(
                    "Employee advances found that should be deducted from salary but are missing additional salary records: {0}. "
                    "Total unclaimed amount: {1}. Please create additional salary records for these advances."
                ).format(
                    frappe.bold(", ".join(advance_names)),
                    frappe.bold(frappe.utils.fmt_money(total_amount))
                ),
                title=_("Employee Advances Not Deducted"),
                indicator="orange",
            )

        if salary_slips_not_created:
            frappe.msgprint(
                _(
                    "Salary Slips already exists for employees {}, and will not be processed by this payroll."
                ).format(frappe.bold(", ".join([emp for emp in salary_slips_not_created]))),
                title=_("Message"),
                indicator="orange",
            )


def create_salary_slips_for_employees(employees, args, publish_progress=True):
    try:
        _create_salary_slips_for_employees(employees, args, publish_progress=publish_progress)
    except Exception as e:
        frappe.db.rollback()
        _mark_payroll_entry_failed(args, e)
    finally:
        frappe.db.commit()
        frappe.publish_realtime("completed_salary_slip_creation", user=frappe.session.user)



def add_leaves(doc):
			
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
