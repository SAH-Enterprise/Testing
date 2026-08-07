frappe.listview_settings['Employee Attendance'] = {
    colwidths: { "subject": 6 },
    onload: function(listview) {
        // Add "Get Attendance" menu item
        listview.page.add_menu_item(__('Get Attendance'), function() {
            var dialog = new frappe.ui.Dialog({
                title: __('Get Attendance'),
                fields: [
                    { 
                        fieldtype: 'Date', 
                        reqd: 1, 
                        fieldname: 'from_date', 
                        label: __("From Date"), 
                        default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
                    },
                    { fieldtype: 'Column Break' },
                    { 
                        fieldtype: 'Date',
                        reqd: 1, 
                        fieldname: 'to_date', 
                        label: __("To Date"), 
                        default: frappe.datetime.get_today(),
                    },
                    { fieldtype: 'Section Break' },
                    { 
                        fieldtype: 'Link', 
                        fieldname: 'employee', 
                        label: __("Employee"),
                        options: "Employee" 
                    },
                    { 
                        fieldtype: 'Link', 
                        fieldname: 'department', 
                        label: __("Department"),
                        options: "Department" 
                    },
                ],
                primary_action: function () {
                    var args = dialog.get_values();
                    if (!args) {
                        return;
                    }
                    // Do not require list-row selection — fetch is driven by from/to dates.
                    frappe.call({
                        method: "hr_vfg.hr_ventureforce_global.doctype.employee_attendance.attendance_connector.get_attendance_long",
                        args: args,
                        freeze: true,
                        freeze_message: __("Queuing biometric attendance fetch..."),
                        callback: function () {
                            frappe.show_alert({
                                message: __("Queued for biometric attendance. It may take a few minutes."),
                                indicator: "green",
                            });
                        },
                    });
                    dialog.hide();
                },
                primary_action_label: __("Submit")
            });
            dialog.show();
        });

        // Add "Refresh" action item
        listview.page.add_action_item(__('Refresh'), function() {
            // Get selected documents
            const selected_docs = listview.get_checked_items();
            if (!selected_docs.length) {
                frappe.msgprint(__('Please select at least one document.'));
                return;
            }

            // Confirm action
            frappe.confirm(
                __('Are you sure you want to refresh the table for the selected records?'),
                function() {
                    let processed_count = 0; // Counter to track completion

                    // Loop through all selected docs
                    selected_docs.forEach(doc => {
                        frappe.call({
                            method: "hr_vfg.hr_ventureforce_global.doctype.employee_attendance.employee_attendance.refresh_table",
                            args: {
                                docname: doc.name
                            },
                            callback: function(response) {
                                processed_count++;
                                if (response.message) {
                                    frappe.msgprint(`Refreshed ${doc.name}: ${response.message}`);
                                }

                                // Refresh List View after all calls are complete
                                if (processed_count === selected_docs.length) {
                                    listview.refresh();
                                }
                            }
                        });
                    });
                }
            );
        });
    }
};
