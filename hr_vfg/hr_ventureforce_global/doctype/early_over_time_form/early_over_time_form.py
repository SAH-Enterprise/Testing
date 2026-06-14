# Copyright (c) 2024, VFG and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate
import calendar


class EarlyOverTimeForm(Document):
	def before_validate(self):
		"""Extract day, month name, and year from date field"""
		if self.date:
			date_obj = getdate(self.date)
			self.day = date_obj.day
			self.month = calendar.month_name[date_obj.month]  # Full month name like "November"
			self.year = date_obj.year
	@frappe.whitelist()
	def get_data(self):
		rec = frappe.db.sql("""
		SELECT p.employee,p.employee_name,c.shift_start,c.date, c.check_in_1, c.estimate_early, c.approved_eot, c.early_over_time, c.name as child_name, p.name as parent_name FROM `tabEmployee Attendance` p
		LEFT JOIN `tabEmployee Attendance Table` c ON c.parent=p.name
		where c.date=%s and c.estimate_early is not null and
		(c.approved_eot IS NULL OR c.approved_eot = '') 
		""",
		# where p.month=%s and p.year=%s and c.date=%s and c.early_ot is not null and c.early_over_time is not null and c.check_in_1 is not null and c.approved_eot is null and c.early_ot > %s """,
		(self.date),as_dict=1)

# for threshould of ot frequency had been added
#  if len(rec)>0:
			# self.early_over_time_form_ct = []

		if len(rec)>0:
			self.early_over_time_form_ct = []
		
		for r in rec:
			allow_ot = frappe.db.get_value("Employee",r.employee,"is_overtime_allowed")
			if allow_ot == 1:
				self.append("early_over_time_form_ct",{
					"employee":r.employee,
					"employee_name":r.employee_name,
					"check_in_1" : r.check_in_1,
					"date": r.date,
					"early_over_time":r.estimate_early,
					"approved_early_over_time":r.estimate_early,
					# "check":r.early_over_time,
					"att_ref":r.parent_name,
					"att_child_ref":r.child_name
				})
		self.save()

	def on_submit(self):
		# Group updates by parent document to avoid reloading the same parent multiple times
		parent_docs = {}
		
		for r in self.early_over_time_form_ct:
			# Update the `approved_eot` field in `Employee Attendance Table` via SQL
			frappe.db.sql("""
			update `tabEmployee Attendance Table` set approved_eot=%s where name=%s
			""",(r.approved_early_over_time,r.att_child_ref))
			
			# Group by parent document
			if r.att_ref not in parent_docs:
				parent_docs[r.att_ref] = []
			parent_docs[r.att_ref].append({
				"child_ref": r.att_child_ref,
				"approved_eot": r.approved_early_over_time
			})
		
		
		# Update each parent document once with all its child updates
		for parent_name, updates in parent_docs.items():
			try:
				# Clear cache to ensure fresh data
				frappe.clear_cache(doctype="Employee Attendance")
				
				# Reload document to get fresh data from DB (not from cache)
				doc = frappe.get_doc("Employee Attendance", parent_name)
				doc.reload()
				
				# Update all child records for this parent
				for update in updates:
					child_row = doc.getone({"name": update["child_ref"]})
					if child_row:
						child_row.approved_eot = update["approved_eot"]
				
				# Save the document - this will trigger validate() and recalculate all totals
				doc.save(ignore_permissions=True)
				
			except Exception as e:
				frappe.log_error(
					f"Error updating Employee Attendance {parent_name} from Early Over Time Form: {str(e)}\n{frappe.get_traceback()}",
					"Early Over Time Form: Update Error"
				)
				frappe.db.rollback()
				frappe.throw(f"Error updating attendance for {parent_name}: {str(e)}")

	
	def on_cancel(self):
		# Group updates by parent document to avoid reloading the same parent multiple times
		parent_docs = {}
		
		for r in self.early_over_time_form_ct:
			# Update the `approved_eot` field in `Employee Attendance Table` via SQL
			frappe.db.sql("""
			update `tabEmployee Attendance Table` set approved_eot='' where name=%s
			""", (r.att_child_ref))
			
			# Group by parent document
			if r.att_ref not in parent_docs:
				parent_docs[r.att_ref] = []
			parent_docs[r.att_ref].append({
				"child_ref": r.att_child_ref
			})
		
		
		# Update each parent document once with all its child updates
		for parent_name, updates in parent_docs.items():
			try:
				# Clear cache to ensure fresh data
				frappe.clear_cache(doctype="Employee Attendance")
				
				# Reload document to get fresh data from DB (not from cache)
				doc = frappe.get_doc("Employee Attendance", parent_name)
				doc.reload()
				
				# Update all child records for this parent
				for update in updates:
					child_row = doc.getone({"name": update["child_ref"]})
					if child_row:
						child_row.approved_eot = ''
				
				# Save the document - this will trigger validate() and recalculate all totals
				doc.save(ignore_permissions=True)
				
			except Exception as e:
				frappe.log_error(
					f"Error updating Employee Attendance {parent_name} from Early Over Time Form (cancel): {str(e)}\n{frappe.get_traceback()}",
					"Early Over Time Form: Cancel Error"
				)
				frappe.db.rollback()
				frappe.throw(f"Error updating attendance for {parent_name}: {str(e)}")
