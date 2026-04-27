// Copyright (c) 2024, VFG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Employee Advance Bulk', {
    refresh: function(frm) {
        // Add custom button if document is submitted
        // Server-side validation will handle checking if employee advances exist and if payment entries can be created
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Create Disbursed Payment'), function() {
                create_disbursed_payment(frm);
            }, __('Actions')).addClass('btn-primary');
        }
    },
    
    get_data: function(frm) {
        frm.call({
            method: 'get_data',
            doc: frm.doc,
            args: {},
            callback: function(r) {
                frm.reload_doc();
            }
        });
    }
});

function create_disbursed_payment(frm) {
    // Show dialog to select payment account and mode of payment
    frappe.prompt([
        {
            'fieldname': 'payment_account',
            'fieldtype': 'Link',
            'label': 'Payment Account',
            'options': 'Account',
            'reqd': 1,
            'description': 'Select the account from which payment will be made'
        },
        {
            'fieldname': 'mode_of_payment',
            'fieldtype': 'Link',
            'label': 'Mode of Payment',
            'options': 'Mode of Payment',
            'reqd': 1,
            'description': 'Select the mode of payment (e.g., Cash, Bank, Cheque)'
        },
        {
            'fieldname': 'payment_entry_posting_date',
            'fieldtype': 'Date',
            'label': __('Posting Date'),
            'reqd': 1,
            'default': frm.doc.posting_date || frappe.datetime.get_today(),
            'description': __('Posting date on the Payment Entry')
        },
        {
            'fieldname': 'payment_entry_posting_time',
            'fieldtype': 'Time',
            'label': __('Posting Time'),
            'reqd': 0,
            'default': frappe.datetime.now_time()
        }
    ], function(values) {
        if (values.payment_account && values.mode_of_payment) {
            // Check if mode of payment requires bank reference fields
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'Mode of Payment',
                    filters: { name: values.mode_of_payment },
                    fieldname: ['type']
                },
                callback: function(r) {
                    if (r.message && r.message.type === 'Bank') {
                        // Show dialog for bank reference fields
                        frappe.prompt([
                            {
                                'fieldname': 'reference_no',
                                'fieldtype': 'Data',
                                'label': 'Reference No',
                                'reqd': 1,
                                'description': 'Bank transaction reference number'
                            },
                            {
                                'fieldname': 'reference_date',
                                'fieldtype': 'Date',
                                'label': 'Reference Date',
                                'reqd': 1,
                                'default': frm.doc.posting_date || frappe.datetime.get_today(),
                                'description': 'Bank transaction reference date'
                            }
                        ], function(bank_values) {
                            // Call server method with bank reference fields
                            create_payment_entries(frm, values.payment_account, values.mode_of_payment, bank_values.reference_no, bank_values.reference_date, values.payment_entry_posting_date, values.payment_entry_posting_time);
                        }, __('Bank Transaction Details'), __('Continue'));
                    } else {
                        // Not a bank mode, proceed without reference fields
                        create_payment_entries(frm, values.payment_account, values.mode_of_payment, null, null, values.payment_entry_posting_date, values.payment_entry_posting_time);
                    }
                }
            });
        }
    }, __('Select Payment Details'), __('Create Payment'));
}

function create_payment_entries(frm, payment_account, mode_of_payment, reference_no, reference_date, payment_entry_posting_date, payment_entry_posting_time) {
    frappe.call({
        method: 'hr_vfg.hr_ventureforce_global.doctype.employee_advance_bulk.employee_advance_bulk.create_disbursed_payment',
        args: {
            docname: frm.doc.name,
            payment_account: payment_account,
            mode_of_payment: mode_of_payment,
            reference_no: reference_no,
            reference_date: reference_date,
            payment_entry_posting_date: payment_entry_posting_date,
            payment_entry_posting_time: payment_entry_posting_time
        },
        callback: function(r) {
            if (r.exc) {
                frappe.msgprint(__('Error: ') + r.exc);
            } else {
                frappe.msgprint(__('Payment entries created successfully!'));
                frm.reload_doc();
                // Refresh the form to hide the button
                frm.refresh();
            }
        }
    });
}


