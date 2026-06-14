# Copyright (c) 2025, VFG and contributors
# For license information, please see license.txt
from frappe import _
import frappe
from frappe.model.document import Document

class EarlyCompensationDateWise(Document):
    @frappe.whitelist()
    def get_data(self):
        # 1. Make sure the date is set
        if not self.compensation_date:
            frappe.throw(_("Please set the Compensation Date first."))

        # 2. Clear out any existing rows
        self.set("early_compensation_date_wise", [])

        # 3. Grab every attendance row marked early on that date
        rows = frappe.db.sql("""
            SELECT
                p.name            AS parent_name,
                c.name            AS child_name,
                p.employee        AS employee,
                p.designation     AS designation,
                p.department      AS department,
                c.check_in_1      AS check_in,
                c.check_out_1     AS check_out
            FROM `tabEmployee Attendance Table` c
            JOIN `tabEmployee Attendance` p
              ON c.parent = p.name
            WHERE c.date = %s
              AND c.early = 1
        """, (self.compensation_date,), as_dict=1)

        # 4. Populate your child table
        for r in rows:
            self.append("early_compensation_date_wise", {
                "employee":          r.employee,
                "designation":       r.designation,
                "department":        r.department,
                "check_in":          r.check_in,
                "check_out":         r.check_out,
                "employee_attendance": r.parent_name,
                "employeee_attendance_table":  r.child_name,
            })

        # 5. Save so the UI shows the new rows
        self.save()

    def on_submit(self):
        # 6. When document is submitted, mark each attendance table row
        for row in self.early_compensation_date_wise:
            # update via SQL for speed
            frappe.db.sql("""
                UPDATE `tabEmployee Attendance Table`
                SET early_compensation = 1
                WHERE name = %s
            """, (row.employeee_attendance_table,))

            # also update via ORM so all hooks fire
            doc = frappe.get_doc("Employee Attendance", row.employee_attendance)
            child = doc.getone({"name": row.employeee_attendance_table})
            child.early_compensation = 1
            doc.save()

