frappe.ui.form.on('Employee Attendance', {
    refresh: function(frm) {
        frm.add_custom_button(__('Refresh'), function() {
            frappe.call({
                method: "hr_vfg.hr_ventureforce_global.doctype.employee_attendance.employee_attendance.refresh_table",
                args: {
                    docname: frm.doc.name
                },
                callback: function(response) {
                    if (response.message) {
                        frappe.msgprint(response.message);
                        frm.reload_doc(); // Reload the form to reflect changes
                    }
                }
            });
        });
    }
    
});
