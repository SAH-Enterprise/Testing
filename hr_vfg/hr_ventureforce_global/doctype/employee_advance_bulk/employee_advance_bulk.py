import frappe
from frappe import _
from frappe.model.document import Document
from datetime import datetime, timedelta


def _set_payment_entry_posting_datetime(pe, posting_date=None, posting_time=None, fallback_date=None):
    """Set Payment Entry posting_date. Payment Entry has no posting_time field in core ERPNext; time is stored in Remarks."""
    pe.posting_date = posting_date or fallback_date
    if posting_time and str(posting_time).strip():
        line = _("Posting time: {0}").format(posting_time)
        existing = (pe.get("remarks") or "").strip()
        pe.remarks = f"{existing}\n{line}".strip() if existing else line

class EmployeeAdvanceBulk(Document):
    def validate(self):
        self.month_and_year()
        self.calculate_total_advance()

    def month_and_year(self):
        date_str = str(self.posting_date)
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")  
        self.day = date_obj.strftime('%A')
        self.month = date_obj.strftime("%B") 
        self.year = date_obj.year

    def calculate_total_advance(self):
        amount = 0
        for i in self.employee_advance_bulk_ct:
            amount += i.amount or 0
        self.total_advance = amount

    @frappe.whitelist()
    def get_data(self):
        # Fetching employee data from `Employee` doctype
        rec = frappe.db.sql("""
            SELECT name, employee_name, department, designation, date_of_joining FROM `tabEmployee`
            WHERE status = 'Active'
        """, as_dict=1)

        # Clear the child table before appending new data
        self.employee_advance_bulk_ct = []

        # Loop through each employee record and append to the child table
        for r in rec:
            self.append('employee_advance_bulk_ct', {
                "employee_name": r['name'], 
                "designation": r.designation,
                "department": r['department'],  # Employee's department
                "date_of_joining": r['date_of_joining']  # Employee's date of joining
            })

        # Save the changes to the document after appending the child table data
        self.save()

    def on_submit(self):
        company = frappe.get_doc("Company", self.company)
        adv_acct  = company.default_employee_advance_account
        curr      = company.default_currency

        for row in self.employee_advance_bulk_ct:
            # — create & submit the Employee Advance only —
            adv = (
                frappe.get_doc({
                    "doctype":                "Employee Advance",
                    "custom_employee_advance_bulk": self.name,
                    "employee":               row.employee_name,
                    "company":                self.company,
                    "posting_date":           self.posting_date,
                    "currency":               curr,
                    "purpose":                self.remarks or "",
                    "exchange_rate":          1,
                    "advance_amount":         row.amount,
                    "mode_of_payment":        "Cash",
                    "advance_account":        adv_acct,
                    "repay_unclaimed_amount_from_salary": 1,
                    # "custom_reference_document": self.doctype,
                    # "custom_reference_voucher": self.name
                })
                .insert()
                .submit()
            )

            # save the employee advance link back on your bulk row
            frappe.db.set_value(row.doctype, row.name, {
                "employee_advance": adv.name
            }, update_modified=False)

        frappe.db.commit()
        frappe.msgprint("Employee Advances created successfully. Use 'Create Disbursed Payment' button to create payment entries.")

    @frappe.whitelist()
    def create_disbursed_payment(
        self,
        payment_account=None,
        mode_of_payment=None,
        reference_no=None,
        reference_date=None,
        payment_entry_posting_date=None,
        payment_entry_posting_time=None,
    ):
        """Create Payment Entry for disbursement after document is submitted"""
        # Get the document if called from JavaScript
        if not hasattr(self, 'name') or not self.name:
            self = frappe.get_doc("Employee Advance Bulk", frappe.form_dict.docname)
            # Get fields from form_dict if available
            if not mode_of_payment:
                mode_of_payment = frappe.form_dict.get('mode_of_payment')
            if not reference_no:
                reference_no = frappe.form_dict.get('reference_no')
            if not reference_date:
                reference_date = frappe.form_dict.get('reference_date')
            if not payment_entry_posting_date:
                payment_entry_posting_date = frappe.form_dict.get('payment_entry_posting_date')
            if payment_entry_posting_time is None:
                payment_entry_posting_time = frappe.form_dict.get('payment_entry_posting_time')
        
        if self.docstatus != 1:
            frappe.throw("Document must be submitted before creating payment entries.")
        
        # Validate mode of payment is provided
        if not mode_of_payment:
            frappe.throw("Mode of Payment is required. Please select a mode of payment in the dialog.")
        
        # Check if mode of payment type is Bank and requires reference fields
        mode_of_payment_type = frappe.get_cached_value("Mode of Payment", mode_of_payment, "type")
        if mode_of_payment_type == "Bank":
            if not reference_no:
                frappe.throw("Reference No is required for bank transactions. Please provide it in the dialog.")
            if not reference_date:
                frappe.throw("Reference Date is required for bank transactions. Please provide it in the dialog.")
        
        company = frappe.get_doc("Company", self.company)
        
        # Get cash account - use the provided payment account or fallback to document account
        cash_acct = payment_account or self.account
        if not cash_acct:
            # Try to get from company settings
            cash_acct = company.default_cash_account
        if not cash_acct:
            # Try to get from company settings directly
            cash_acct = frappe.db.get_value("Company", self.company, "default_cash_account")
        if not cash_acct:
            frappe.throw("Payment account not found. Please select a payment account or set the account field in the document.")
        
        # Verify the cash account exists
        if not frappe.db.exists("Account", cash_acct):
            frappe.throw(f"Cash account '{cash_acct}' does not exist in the database.")
        
        # Get employee advance account
        adv_acct = company.default_employee_advance_account
        if not adv_acct:
            frappe.throw("Employee advance account not found. Please set default employee advance account in Company settings.")
        
        # Verify the employee advance account exists
        if not frappe.db.exists("Account", adv_acct):
            frappe.throw(f"Employee advance account '{adv_acct}' does not exist in the database.")
        
        curr = company.default_currency

        # Debug information
        print(f"DEBUG: Company: {self.company}")
        print(f"DEBUG: Selected Payment Account: {payment_account}")
        print(f"DEBUG: Document Account Field: {self.account}")
        print(f"DEBUG: Company Default Cash Account: {company.default_cash_account}")
        print(f"DEBUG: Final Cash Account: {cash_acct}")
        print(f"DEBUG: Employee Advance Account: {adv_acct}")
        print(f"DEBUG: Currency: {curr}")

        payment_entries_created = 0

        for row in self.employee_advance_bulk_ct:
            if row.employee_advance and not row.payment_entry:
                # Verify employee exists
                if not frappe.db.exists("Employee", row.employee_name):
                    frappe.throw(f"Employee '{row.employee_name}' does not exist in the database.")
                
                # Verify employee advance exists
                if not frappe.db.exists("Employee Advance", row.employee_advance):
                    frappe.throw(f"Employee Advance '{row.employee_advance}' does not exist in the database.")
                
                # Get the employee advance document
                adv = frappe.get_doc("Employee Advance", row.employee_advance)
                
                # Calculate outstanding amount to ensure we don't allocate more than available
                outstanding_amount = adv.advance_amount - (adv.paid_amount or 0)
                # Ensure allocated_amount doesn't exceed outstanding_amount
                allocated_amount = min(row.amount, outstanding_amount)
                
                if allocated_amount <= 0:
                    frappe.msgprint(f"Skipping payment for {row.employee_name}: No outstanding amount available.")
                    continue
                
                # — create the Payment Entry as an advance —
                pe = frappe.new_doc("Payment Entry")
                pe.payment_type               = "Pay"
                pe.party_type                 = "Employee"
                pe.party                      = row.employee_name
                pe.party_name                 = frappe.get_value("Employee",
                                                               row.employee_name,
                                                               "employee_name")
                pe.company                    = self.company
                _set_payment_entry_posting_datetime(
                    pe,
                    posting_date=payment_entry_posting_date,
                    posting_time=payment_entry_posting_time,
                    fallback_date=self.posting_date,
                )

                pe.paid_from                  = cash_acct
                pe.paid_from_account_currency = curr
                pe.paid_to                    = adv_acct
                pe.paid_to_account_currency   = curr

                pe.paid_amount      = allocated_amount
                pe.received_amount  = allocated_amount

                pe.exchange_rate        = 1
                pe.source_exchange_rate = 1
                pe.target_exchange_rate = 1

                pe.custom_employee_advance_bulk = self.name

                # Validate required fields before saving
                if not pe.paid_from:
                    frappe.throw(f"Paid From account is missing for employee {row.employee_name}")
                if not pe.paid_to:
                    frappe.throw(f"Paid To account is missing for employee {row.employee_name}")
                if not pe.party:
                    frappe.throw(f"Party is missing for employee {row.employee_name}")

                # Use the user-selected mode of payment
                pe.mode_of_payment = mode_of_payment
                
                # Set reference_no and reference_date if mode of payment type is Bank
                if mode_of_payment_type == "Bank":
                    pe.reference_no = reference_no
                    pe.reference_date = reference_date

                # **this flag** tells ERPNext these References are Advances
                pe.is_advance = 1

                # **append into the _References_ table**, not "advances"
                pe.append("references", {
                    "reference_doctype":  "Employee Advance",
                    "reference_name":     adv.name,
                    "total_amount":       adv.advance_amount,
                    "outstanding_amount": outstanding_amount,
                    "allocated_amount":   allocated_amount
                })

                pe.insert()
                pe.submit()

                # tell the Advance to recalc its paid_amount & status
                adv.reload()
                adv.set_total_advance_paid()
                adv.save()
                
                # Force update the Employee Advance status
                self.update_employee_advance_status(adv.name, allocated_amount)
                
                # Also trigger ERPNext's standard payment allocation
                pe.reload()
                pe.set_total_allocated_amount()
                pe.set_unallocated_amount()
                pe.save()

                # save the payment entry link back on your bulk row
                frappe.db.set_value(row.doctype, row.name, {
                    "payment_entry": pe.name
                }, update_modified=False)

                payment_entries_created += 1

        frappe.db.commit()
        
        if payment_entries_created > 0:
            frappe.msgprint(f"Successfully created {payment_entries_created} payment entries for disbursement.")
        else:
            frappe.msgprint("No payment entries were created. All advances may already have payment entries.")
        
        return {
            "payment_entries_created": payment_entries_created,
            "message": f"Successfully created {payment_entries_created} payment entries for disbursement."
        }

    def update_employee_advance_status(self, advance_name, paid_amount):
        """Update Employee Advance status after Payment Entry submission"""
        try:
            # Get the Employee Advance document
            adv = frappe.get_doc("Employee Advance", advance_name)
            
            print(f"DEBUG: Before update - Employee Advance {advance_name}")
            print(f"DEBUG: Current paid_amount: {adv.paid_amount}")
            print(f"DEBUG: Advance amount: {adv.advance_amount}")
            print(f"DEBUG: Current status: {adv.status}")
            print(f"DEBUG: Adding paid_amount: {paid_amount}")
            
            # Update the paid amount
            current_paid = adv.paid_amount or 0
            new_paid = current_paid + paid_amount
            adv.paid_amount = new_paid
            
            # Update status based on paid amount
            if new_paid >= adv.advance_amount:
                adv.status = "Paid"
            elif new_paid > 0:
                adv.status = "Partially Paid"
            else:
                adv.status = "Unpaid"
            
            print(f"DEBUG: After update - New paid_amount: {new_paid}, New status: {adv.status}")
            
            # Save the changes
            adv.save(ignore_permissions=True)
            
            print(f"DEBUG: Updated Employee Advance {advance_name} - Paid Amount: {new_paid}, Status: {adv.status}")
            
        except Exception as e:
            frappe.log_error(f"Error updating Employee Advance status: {str(e)}", "Employee Advance Status Update Error")
            print(f"ERROR: Failed to update Employee Advance {advance_name}: {str(e)}")

    

@frappe.whitelist()
def create_disbursed_payment(
    docname,
    payment_account=None,
    mode_of_payment=None,
    reference_no=None,
    reference_date=None,
    payment_entry_posting_date=None,
    payment_entry_posting_time=None,
):
    """Standalone function to create disbursed payment entries"""
    doc = frappe.get_doc("Employee Advance Bulk", docname)
    return doc.create_disbursed_payment(
        payment_account,
        mode_of_payment,
        reference_no,
        reference_date,
        payment_entry_posting_date,
        payment_entry_posting_time,
    )

@frappe.whitelist()
def get_dashboard_data():
    """Get dashboard statistics for Employee Advance Bulk"""
    try:
        # Count all Employee Advances
        employee_advances_count = frappe.db.count("Employee Advance", {
            "docstatus": 1
        })
        
        # Count all Payment Entries that are advances
        payment_entries_count = frappe.db.count("Payment Entry", {
            "is_advance": 1,
            "docstatus": 1
        })
        
        # Count submitted Employee Advance Bulk documents
        bulk_documents_count = frappe.db.count("Employee Advance Bulk", {
            "docstatus": 1
        })
        
        return {
            "employee_advances": employee_advances_count,
            "payment_entries": payment_entries_count,
            "bulk_documents": bulk_documents_count
        }
    except Exception as e:
        frappe.log_error(f"Error getting dashboard data: {str(e)}", "Employee Advance Bulk Dashboard Error")
        return {
            "employee_advances": 0,
            "payment_entries": 0,
            "bulk_documents": 0
        }