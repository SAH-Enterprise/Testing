# Copyright (c) 2024, VFG and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class LateCompensationEmployeeWise(Document):
	@frappe.whitelist()
	def get_data1(self):
			rec = frappe.db.sql("""select c.date, p.employee,p.employee_name, c.late_sitting, c.date,c.check_in_1, c.late_sitting,
					c.late_coming_hours,c.late, c.late1, c.name as child_name, p.name as parent_name from `tabEmployee Attendance` p
					LEFT JOIN `tabEmployee Attendance Table` c ON c.parent=p.name
					 where p.month=%s and p.year=%s and p.employee=%s and c.late = "1"
					   """, (self.month, self.year, self.employee), as_dict=1)
			if len(rec)>0:
				self.detail=[]
			for r in rec:
				self.append("late_coming_adjustment_ct",{
					"employee": r.employee,
					"date": r.date,
					"late_sitting" : r.late_sitting,
					"check_in_1": r.check_in_1,
					"late_coming_hours":r.late_coming_hours,
					"late": r.late,
					"late1":1,
					"att_ref": r.parent_name,
					"att_child_ref":r.child_name
				})
			self.save()
	
	def on_submit(self):
		for r in self.late_coming_adjustment_ct:
			frappe.db.sql("""
				update `tabEmployee Attendance Table` 
				set late1= %s
				where name= %s
			""",(r.late,r.att_child_ref))
			doc = frappe.get_doc("Employee Attendance",r.att_ref)
			doc.save()

	def on_cancel(self):
		for r in self.late_coming_adjustment_ct:
			frappe.db.sql("""
				update `tabEmployee Attendance Table`
				set late1 = 0
				where name = %s
				
			""", (r.att_child_ref))
			doc = frappe.get_doc("Employee Attendance", r.att_ref)
			doc.save()