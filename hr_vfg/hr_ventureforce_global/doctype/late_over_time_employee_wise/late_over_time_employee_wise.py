# Copyright (c) 2024, VFG and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class LateOverTimeEmployeeWise(Document):
	@frappe.whitelist()
	def get_data(self):
		# Fetch data using SQL query
		rec = frappe.db.sql("""
		select p.employee, p.employee_name, p.designation, c.date, c.late_sitting, c.approved_ot1, c.estimated_late,
			c.name as child_name, p.name as parent_name 
		from `tabEmployee Attendance` p
		LEFT JOIN `tabEmployee Attendance Table` c ON c.parent=p.name
		where p.month = %s and p.year = %s and p.employee=%s and 
			(c.estimated_late IS NOT NULL AND c.estimated_late != '') and 
			(c.approved_ot1 = '' or c.approved_ot1 is null or c.approved_ot1 = '00:00:00')
		ORDER BY c.date ASC  -- Sort by date in ascending order
		LIMIT 50  -- Fetch only 50 records at a time
		""", (self.month, self.year, self.employee), as_dict=1)

		# Debug log for SQL results
		# frappe.log_error(f"SQL Result: {rec}", "Debugging SQL")

		if rec:
			self.late_over_time_employee_wise_ct = []
			for r in rec:
				allow_ot = frappe.db.get_value('Employee', r.employee, 'is_overtime_allowed')
				
				# Allow overtime only if the employee is eligible
				# if allow_ot == 1 and r.estimated_late:
				if allow_ot == 1:
					frappe.log_error(f"Appending: Employee: {r.employee}, Overtime: {r.estimated_late}, Date: {r.date}")
					
					# Append the record to the child table
					self.append("late_over_time_employee_wise_ct", {
						"employee": r.employee,
						"date": r.date,
						"late_sitting": r.estimated_late,
						# "late_sitting": r.estimated_late,
						"approved_ot": r.estimated_late,
						"employee_name": r.employee_name,
						"att_ref": r.parent_name,
						"att_child_ref": r.child_name
					})
			self.save()


	def on_submit(self):
		for r in self.late_over_time_employee_wise_ct:
			# Update the `approved_ot1` field in `Employee Attendance Table`
			frappe.db.sql("update `tabEmployee Attendance Table` set approved_ot1=%s where name=%s", 
						  (r.approved_ot, r.att_child_ref))

			# Reload and update the parent document
			doc = frappe.get_doc("Employee Attendance", r.att_ref)
			child_row = doc.getone({"name": r.att_child_ref})
			child_row.approved_ot1 = r.approved_ot
			doc.save()

			# Reload to verify update
			doc.reload()
			# frappe.log_error(f"Updated approved_ot1: {child_row.approved_ot1}")

	def on_cancel(self):
		for r in self.late_over_time_employee_wise_ct:
			# Update the `approved_ot1` field in `Employee Attendance Table`
			frappe.db.sql("update `tabEmployee Attendance Table` set approved_ot1='' where name=%s", 
						  (r.att_child_ref,))

			doc = frappe.get_doc("Employee Attendance", r.att_ref)
			child_row = doc.getone({"name": r.att_child_ref})
			child_row.approved_ot1 = ''
			doc.save()

			# Reload to verify update
			doc.reload()
			# frappe.log_error(f"Updated approved_ot1: {child_row.approved_ot1}")

