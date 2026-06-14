import frappe
from frappe.model.document import Document

class AbsentAdjustmentWithHoliday(Document):
    @frappe.whitelist()
    def get_data1(self):
        frappe.logger().info(f"get_data1 called with absent_date: {self.absent_date}")

        rec = frappe.db.sql("""
            select p.employee, p.employee_name, p.designation, c.date, c.check_in_1, c.check_out_1, c.absent, c.name as child_name, p.name as parent_name 
            from `tabEmployee Attendance` p
            LEFT JOIN `tabEmployee Attendance Table` c ON c.parent=p.name
            where c.date=%s and c.absent = 1
        """, (self.absent_date, ), as_dict=1)

        if rec:
            self.absent_data = []
            for r in rec:
                self.append("absent_data", {
                    "date": r.date,
                    "check_in": r.check_in_1,
                    "check_out": r.check_out_1,
                    "absent": r.absent,
                    "att_ref": r.parent_name,
                    "att_child_ref": r.child_name
                })
            self.save()
            
    @frappe.whitelist()
    def get_data2(self):
        frappe.logger().info(f"get_data1 called with adjustment_date: {self.adjustment_date}")

        rec1 = frappe.db.sql("""
            select p.employee, p.employee_name, p.designation,c.estimated_late, c.difference1,c.late_sitting,c.approved_ot1, c.holiday_adjustment, c.date,c.weekly_off, c.check_in_1, c.check_out_1, c.absent, c.name as child_name, p.name as parent_name 
            from `tabEmployee Attendance` p
            LEFT JOIN `tabEmployee Attendance Table` c ON c.parent=p.name
            where c.date=%s and c.weekly_off = 1 and c.check_in_1 is not null and c.check_in_1 != '' and c.check_out_1 is not null and c.check_out_1 != '' and c.holiday_adjustment = 0
        """, (self.adjustment_date, ), as_dict=1)

        if rec1:
            self.adjustment_data = []
            for s in rec1:
                self.append("adjustment_data", {
                    "date": s.date,
                    "check_in": s.check_in_1,
                    "check_out": s.check_out_1,
                    "absent": s.absent,
                    "att_ref": s.parent_name,
                    "att_child_ref": s.child_name
                })
            self.save()
            
    def on_submit(self):
        for s in self.adjustment_data:
            frappe.db.sql("""
				update `tabEmployee Attendance Table` 
				set holiday_adjustment = %s, 
					estimated_late = "", 
					approved_ot1 = ""
				where name = %s
			""", (s.holiday_adjustment, s.att_child_ref))
            
            doc = frappe.get_doc("Employee Attendance", s.att_ref)
            child_row = doc.getone({"name": s.att_child_ref})
            child_row.holiday_adjustment = s.holiday_adjustment
            child_row.estimated_late = ""
            doc.save()
            doc.reload()