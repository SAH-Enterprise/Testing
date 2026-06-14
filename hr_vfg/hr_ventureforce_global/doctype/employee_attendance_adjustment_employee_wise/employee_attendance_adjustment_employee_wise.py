# Copyright (c) 2024, VFG and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EmployeeAttendanceAdjustmentEmployeeWise(Document):
	@frappe.whitelist()
	def get_data(self):
		"""Populate rows for the child table based on adjustment_type."""
		# Clear any existing rows
		self.employee_attendance_adjustment_employee_wise_ct = []

		# Build the SQL “WHERE” fragment for missing‐punch vs. all‐punches
		if self.adjustment_type == "Validate Check In/ Check Out":
			# No extra filter — pull every check‐in/out for the month
			missing_filter = ""
		else:
			# Only rows where one of check_in_1/check_out_1 is NULL
			missing_filter = """
				AND (
					(c.check_in_1 IS NULL AND c.check_out_1 IS NOT NULL)
					OR
					(c.check_in_1 IS NOT NULL AND c.check_out_1 IS NULL)
				)
			"""

		# Fetch the records
		rec = frappe.db.sql(f"""
			SELECT
				p.employee,
				p.employee_name,
				p.month,
				p.year,
				p.designation,
				c.date,
				c.check_in_1,
				c.check_out_1,
				p.name    AS parent_name,
				c.name    AS child_name
			FROM `tabEmployee Attendance` p
			LEFT JOIN `tabEmployee Attendance Table` c
			  ON c.parent = p.name
			WHERE
				p.month    = %s
				AND p.year = %s
				AND p.employee = %s
				{missing_filter}
			ORDER BY c.date
		""", (self.month, self.year, self.employee), as_dict=1)

		# Append each row into the child table
		for r in rec:
			self.append("employee_attendance_adjustment_employee_wise_ct", {
				"date":              r.date,
				"check_in":          r.check_in_1 or "",
				"actual_check_in":   r.check_in_1 or "",
				"check_out":         r.check_out_1 or "",
				"actual_check_out":  r.check_out_1 or "",
				# only mark update flags if there was an original value
				"update_check_in":   1 if r.check_in_1 else 0,
				"update_check_out":  1 if r.check_out_1 else 0,
				"att_ref":           r.parent_name,
				"att_child_ref":     r.child_name
			})

		# Save once at the end
		self.save()

	def on_submit(self):
		
		hr_settings = frappe.get_single('V HR Settings')
		threshold = hr_settings.absent_threshould_missing_punch or 0
		
		for r in self.employee_attendance_adjustment_employee_wise_ct:
			# Update the `approved_ot1` field in `Employee Attendance Table`
			frappe.db.sql("update `tabEmployee Attendance Table` set check_in_1=%s , check_out_1=%s where name=%s", 
						  (r.check_in, r.check_out, r.att_child_ref))

			# Reload and update the parent document
			doc = frappe.get_doc("Employee Attendance", r.att_ref)
			child_row = doc.getone({"name": r.att_child_ref})
			child_row.check_in_1 = r.check_in
			child_row.check_out_1 = r.check_out
			# doc.refreshed = 1 if doc.refreshed == 0 else 0

			
			
			missing = doc.total_missing or 0
			doc.mark_absent_on_missing = max(0, missing - threshold)

			if r.update_check_in == 1 :
				child_row.check_in_updated = 1
			if r.update_check_out == 1:	
				child_row.check_out_updated = 1

			doc.save()

			# Reload to verify update
			# doc.reload()
			# frappe.log_error(f"Updated approved_ot1: {child_row.approved_ot1}")



	def on_cancel(self):
		for r in self.employee_attendance_adjustment_employee_wise_ct:
			
			frappe.db.sql("update `tabEmployee Attendance Table` set check_in_1='', check_out_1='' where name=%s", 
						  (r.att_child_ref,))

			doc = frappe.get_doc("Employee Attendance", r.att_ref)
			child_row = doc.getone({"name": r.att_child_ref})
			child_row.check_in_1 = ''
			child_row.check_out_1 = ''
			doc.save()


			doc.reload()
			# frappe.log_error(f"Updated approved_ot1: {child_row.approved_ot1}")
			# frappe.log_error(f"Updated approved_ot1: {child_row.approved_ot1}")




	def on_submit(self):
		
		hr_settings = frappe.get_single('V HR Settings')
		threshold = hr_settings.absent_threshould_missing_punch or 0
		
		for r in self.employee_attendance_adjustment_employee_wise_ct:
			# Update the `approved_ot1` field in `Employee Attendance Table`
			frappe.db.sql("update `tabEmployee Attendance Table` set check_in_1=%s , check_out_1=%s where name=%s", 
						  (r.check_in, r.check_out, r.att_child_ref))

			# Reload and update the parent document
			doc = frappe.get_doc("Employee Attendance", r.att_ref)
			child_row = doc.getone({"name": r.att_child_ref})
			child_row.check_in_1 = r.check_in
			child_row.check_out_1 = r.check_out
			# doc.refreshed = 1 if doc.refreshed == 0 else 0

			
			
			missing = doc.total_missing or 0
			doc.mark_absent_on_missing = max(0, missing - threshold)

			if r.update_check_in == 1 :
				child_row.check_in_updated = 1
			if r.update_check_out == 1:	
				child_row.check_out_updated = 1

			doc.save()

			# Reload to verify update
			# doc.reload()
			# frappe.log_error(f"Updated approved_ot1: {child_row.approved_ot1}")



	def on_cancel(self):
		for r in self.employee_attendance_adjustment_employee_wise_ct:
			
			frappe.db.sql("update `tabEmployee Attendance Table` set check_in_1='', check_out_1='' where name=%s", 
						  (r.att_child_ref,))

			doc = frappe.get_doc("Employee Attendance", r.att_ref)
			child_row = doc.getone({"name": r.att_child_ref})
			child_row.check_in_1 = ''
			child_row.check_out_1 = ''
			doc.save()


			doc.reload()
			# frappe.log_error(f"Updated approved_ot1: {child_row.approved_ot1}")
			# frappe.log_error(f"Updated approved_ot1: {child_row.approved_ot1}")


