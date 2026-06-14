# Copyright (c) 2024, VFG and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _

class AttendanceAdjustments(Document):
    @frappe.whitelist()
    def get_data(self):
        # ensure adjustment_date and adjustment_type are set
        if not self.adjustment_date:
            frappe.throw(_("Please set the Adjustment Date before fetching data."))
        if not self.adjustment_type:
            frappe.throw(_("Please select an Adjustment Type."))

        # build base query
        base_sql = """
            SELECT
                p.employee,
                p.employee_name,
                p.month,
                p.year,
                p.designation,
                c.date,
                c.check_in_1,
                c.check_out_1,
                p.name   AS parent_name,
                c.name   AS child_name
            FROM `tabEmployee Attendance` p
            LEFT JOIN `tabEmployee Attendance Table` c
              ON c.parent = p.name
            WHERE c.date = %s
        """

        # add filter for missing check-ins/outs only if that adjustment_type is selected
        if self.adjustment_type == "Missing Check In/ Check Out":
            base_sql += """
              AND (
                (c.check_in_1 IS NULL AND c.check_out_1 IS NOT NULL)
                OR
                (c.check_in_1 IS NOT NULL AND c.check_out_1 IS NULL)
              )
            """
        # if you instead want only fully existing records for validation,
        # uncomment the following:
        # elif self.adjustment_type == "Validate Check In/ Check Out":
        #     base_sql += " AND c.check_in_1 IS NOT NULL AND c.check_out_1 IS NOT NULL"

        # run query
        recs = frappe.db.sql(base_sql, (self.adjustment_date,), as_dict=1)

        # clear and repopulate child table
        self.set("attendance_adjustments_ct", [])
        for r in recs:
            self.append("attendance_adjustments_ct", {
                "employee":          r.employee,
                "actual_check_in":   r.check_in_1,
                "check_in":          r.check_in_1,
                "actual_check_out":  r.check_out_1,
                "check_out":         r.check_out_1,
                "att_ref":           r.parent_name,
                "att_child_ref":     r.child_name
            })

        # save draft with populated rows
        self.save()

    def on_submit(self):
        import traceback
        
        print("=" * 80)
        print("=== Attendance Adjustments on_submit STARTED ===")
        print(f"Document: {self.name}")
        print(f"Total rows in attendance_adjustments_ct: {len(self.attendance_adjustments_ct)}")
        print("=" * 80)
        
        frappe.log_error(
            f"=== Attendance Adjustments on_submit STARTED ===\n"
            f"Document: {self.name}\n"
            f"Total rows in attendance_adjustments_ct: {len(self.attendance_adjustments_ct)}",
            "Attendance Adjustments: on_submit START"
        )
        
        # Group updates by parent document to avoid reloading the same parent multiple times
        parent_docs = {}
        
        # First, collect all updates grouped by parent document
        print("\n[Step 1] Collecting updates from child table...")
        frappe.log_error("Step 1: Collecting updates from child table", "Attendance Adjustments: Step 1")
        for idx, row in enumerate(self.attendance_adjustments_ct):
            print(f"  Row {idx}: att_ref={row.att_ref}, att_child_ref={row.att_child_ref}, "
                  f"check_in={row.check_in}, check_out={row.check_out}")
            frappe.log_error(
                f"Row {idx}: att_ref={row.att_ref}, att_child_ref={row.att_child_ref}, "
                f"check_in={row.check_in}, check_out={row.check_out}",
                f"Attendance Adjustments: Row {idx}"
            )
            
            if not row.att_ref or not row.att_child_ref:
                print(f"  ⚠️ Row {idx} skipped: Missing att_ref or att_child_ref")
                frappe.log_error(
                    f"Row {idx} skipped: Missing att_ref or att_child_ref",
                    "Attendance Adjustments: Skipped Row"
                )
                continue
                
            if row.att_ref not in parent_docs:
                parent_docs[row.att_ref] = []
            
            parent_docs[row.att_ref].append({
                "child_name": row.att_child_ref,
                "check_in": row.check_in,
                "check_out": row.check_out
            })
        
        print(f"\n[Step 2] Collected {len(parent_docs)} parent documents to update")
        frappe.log_error(
            f"Step 2: Collected {len(parent_docs)} parent documents to update",
            "Attendance Adjustments: Step 2"
        )
        
        # Update each parent document with all its child updates
        for parent_name, updates in parent_docs.items():
            try:
                print(f"\n{'=' * 80}")
                print(f"[Step 3] Processing parent document: {parent_name}")
                print(f"Number of child updates: {len(updates)}")
                print(f"{'=' * 80}")
                frappe.log_error(
                    f"Step 3: Processing parent document: {parent_name}\n"
                    f"Number of child updates: {len(updates)}",
                    f"Attendance Adjustments: Processing {parent_name}"
                )
                
                # Clear cache first to ensure fresh data
                print("[Step 3.1] Clearing cache...")
                frappe.log_error("Step 3.1: Clearing cache", f"Attendance Adjustments: {parent_name} - Clear Cache")
                frappe.clear_cache(doctype="Employee Attendance")
                
                # Get the parent document
                print(f"[Step 3.2] Loading parent document: {parent_name}")
                frappe.log_error("Step 3.2: Loading parent document", f"Attendance Adjustments: {parent_name} - Load Doc")
                doc = frappe.get_doc("Employee Attendance", parent_name)
                print(f"[Step 3.3] Document loaded successfully")
                print(f"  Document name: {doc.name}")
                print(f"  Number of child records: {len(doc.get('table1', []))}")
                frappe.log_error(
                    f"Step 3.3: Document loaded successfully\n"
                    f"Document name: {doc.name}\n"
                    f"Number of child records: {len(doc.get('table1', []))}",
                    f"Attendance Adjustments: {parent_name} - Doc Loaded"
                )
                
                # Update all child records for this parent
                print(f"[Step 3.4] Updating child records...")
                frappe.log_error("Step 3.4: Updating child records", f"Attendance Adjustments: {parent_name} - Update Children")
                for update_idx, update in enumerate(updates):
                    print(f"  Updating child {update_idx + 1}/{len(updates)}:")
                    print(f"    child_name: {update['child_name']}")
                    print(f"    check_in: {update['check_in']}")
                    print(f"    check_out: {update['check_out']}")
                    frappe.log_error(
                        f"Updating child {update_idx + 1}/{len(updates)}:\n"
                        f"  child_name: {update['child_name']}\n"
                        f"  check_in: {update['check_in']}\n"
                        f"  check_out: {update['check_out']}",
                        f"Attendance Adjustments: {parent_name} - Child {update_idx + 1}"
                    )
                    
                    child = doc.getone({"name": update["child_name"]})
                    if child:
                        print(f"    ✓ Child found!")
                        print(f"      Old values: check_in_1={child.check_in_1}, check_out_1={child.check_out_1}")
                        frappe.log_error(
                            f"Child found. Old values: check_in_1={child.check_in_1}, check_out_1={child.check_out_1}",
                            f"Attendance Adjustments: {parent_name} - Child Found"
                        )
                        child.check_in_1 = update["check_in"]
                        child.check_out_1 = update["check_out"]
                        print(f"      New values: check_in_1={child.check_in_1}, check_out_1={child.check_out_1}")
                        frappe.log_error(
                            f"Child updated. New values: check_in_1={child.check_in_1}, check_out_1={child.check_out_1}",
                            f"Attendance Adjustments: {parent_name} - Child Updated"
                        )
                    else:
                        available_names = [c.name for c in doc.get('table1', [])]
                        print(f"    ✗ ERROR: Child record {update['child_name']} not found!")
                        print(f"      Available child names: {available_names}")
                        frappe.log_error(
                            f"ERROR: Child record {update['child_name']} not found in parent {parent_name}\n"
                            f"Available child names: {available_names}",
                            "Attendance Adjustments: Child Record Not Found"
                        )
                
                # Save the document - this will trigger validate() and recalculate all totals
                print(f"[Step 3.5] Saving parent document...")
                frappe.log_error("Step 3.5: Saving parent document", f"Attendance Adjustments: {parent_name} - Save")
                doc.save(ignore_permissions=True)
                print(f"[Step 3.6] Document saved, committing...")
                frappe.log_error("Step 3.6: Document saved, committing", f"Attendance Adjustments: {parent_name} - Commit")
                print(f"✓ SUCCESS: Parent document {parent_name} updated successfully!")
                frappe.log_error(
                    f"SUCCESS: Parent document {parent_name} updated successfully",
                    f"Attendance Adjustments: {parent_name} - SUCCESS"
                )
                
            except Exception as e:
                error_traceback = traceback.format_exc()
                print(f"\n{'!' * 80}")
                print(f"✗ ERROR updating Employee Attendance {parent_name}:")
                print(f"  Error message: {str(e)}")
                print(f"  Error type: {type(e).__name__}")
                print(f"  Traceback:")
                print(error_traceback)
                print(f"{'!' * 80}\n")
                frappe.log_error(
                    f"ERROR updating Employee Attendance {parent_name}:\n"
                    f"Error message: {str(e)}\n"
                    f"Error type: {type(e).__name__}\n"
                    f"Traceback:\n{error_traceback}",
                    "Attendance Adjustments: Update Error"
                )
                frappe.db.rollback()
                frappe.throw(_("Error updating attendance for {0}: {1}").format(parent_name, str(e)))
        
        print(f"\n{'=' * 80}")
        print(f"=== Attendance Adjustments on_submit COMPLETED ===")
        print(f"Document: {self.name}")
        print(f"{'=' * 80}\n")
        frappe.log_error(
            f"=== Attendance Adjustments on_submit COMPLETED ===\n"
            f"Document: {self.name}",
            "Attendance Adjustments: on_submit END"
        )
