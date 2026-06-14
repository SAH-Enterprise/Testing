# Copyright (c) 2024, VFG and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EarlyOvertimeEmployeeWise(Document):
	@frappe.whitelist()
	def get_data(self):
		rec = frappe.db.sql("""
			SELECT p.employee,p.employee_name,c.shift_start,c.date, c.check_in_1, c.estimate_early, c.early_over_time, c.name as child_name, p.name as parent_name FROM `tabEmployee Attendance` p
			LEFT JOIN `tabEmployee Attendance Table` c ON c.parent=p.name
			WHERE p.month=%s and p.year=%s and p.employee=%s and c.estimate_early is not null and c.approved_eot is null
		""",(self.month,self.year,self.employee),as_dict=1)

		if len(rec)>0:
				self.early_over_time_form_ct = []
			
		for r in rec:
				allow_ot = frappe.db.get_value("Employee",r.employee,"is_overtime_allowed")
				if allow_ot == 1:
					self.append("early_over_time_form_ct",{
						"employee":r.employee,
						"employee_name":r.employee_name,
						"date":r.date,
						"check_in_1" : r.check_in_1,
						"early_over_time":r.estimate_early,
						"approved_early_over_time":r.estimate_early,
						# "check":r.early_over_time,
						"att_ref":r.parent_name,
						"att_child_ref":r.child_name
					})
		self.save()

	def on_submit(self):
		for r in self.early_over_time_form_ct:
			# frappe.db.sql("""
			# update `tabEmployee Attendance Table` set approved_early_over_time=%s where name=%s
			# """,(r.approved_early_over_time,r.att_child_ref))

			frappe.db.sql("""
			update `tabEmployee Attendance Table` set approved_eot=%s where name=%s
			""",(r.approved_early_over_time,r.att_child_ref))
			doc = frappe.get_doc("Employee Attendance",r.att_ref)
			doc.save()

	def on_cancel(self):
		for r in self.early_over_time_form_ct:
            # Update the approved_eot field to an empty string in the Employee Attendance Table
			frappe.db.sql("""
                UPDATE `tabEmployee Attendance Table` 
                SET approved_eot = '' 
                WHERE name = %s
            """, (r.att_child_ref,))

            # Reload the Employee Attendance document to reflect the changes
			doc = frappe.get_doc("Employee Attendance", r.att_ref)
			doc.save()

        # Optionally, you can log the cancellation for debugging purposes
        # frappe.log_error(f"Canceled Early Overtime for: {self.employee} on {self.date}", "EarlyOvertimeEmployeeWise")
