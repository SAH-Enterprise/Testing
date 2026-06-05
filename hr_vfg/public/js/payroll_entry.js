// File: hr_vfg/hr_ventureforce_global/doctype/payroll_entry/payroll_entry.js

function get_payroll_error_text(html) {
    return $("<div>").html(html || "").text().trim();
}

function get_payroll_error_prompt(frm) {
    const error = get_payroll_error_text(frm.doc.error_message);

    return [
        "Explain this ERPNext Payroll Entry error in easy language and tell me how to fix it.",
        "",
        `Payroll Entry: ${frm.doc.name}`,
        `Company: ${frm.doc.company || ""}`,
        `Period: ${frm.doc.start_date || ""} to ${frm.doc.end_date || ""}`,
        "",
        "Error:",
        error,
    ].join("\n");
}

function copy_payroll_error(text) {
    if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text);
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
    return Promise.resolve();
}

function show_payroll_failure_message(frm) {
    if (frm.doc.status !== "Failed" || !frm.doc.error_message) {
        return;
    }

    const error = get_payroll_error_text(frm.doc.error_message);
    const intro = __(
        "Payroll could not be completed. Please fix the issue below, then run payroll again."
    );

    setTimeout(() => {
        frm.set_intro(intro, "red");

        frm.add_custom_button(__("Copy Payroll Error"), () => {
            copy_payroll_error(get_payroll_error_prompt(frm)).then(() => {
                frappe.show_alert({
                    message: __("Payroll error copied. Paste it into AI or send it to support."),
                    indicator: "green",
                });
            });
        }, __("Actions"));
    });

    if (frm.__hr_vfg_payroll_failure_message_shown) {
        return;
    }

    frm.__hr_vfg_payroll_failure_message_shown = true;
    frappe.msgprint({
        title: __("Payroll Issue"),
        indicator: "red",
        message: `
            <p>${intro}</p>
            <pre style="white-space: pre-wrap; max-height: 220px; overflow: auto;">${frappe.utils.escape_html(error)}</pre>
        `,
        primary_action: {
            label: __("Copy for AI"),
            action() {
                copy_payroll_error(get_payroll_error_prompt(frm)).then(() => {
                    frappe.hide_msgprint();
                    frappe.show_alert({
                        message: __("Payroll error copied. Paste it into AI or send it to support."),
                        indicator: "green",
                    });
                });
            },
        },
    });
}

frappe.ui.form.on("Payroll Entry", {
    refresh: function(frm) {
        show_payroll_failure_message(frm);

        // Add a “Check Attendance” button under the Actions menu
        if (!frm.custom_buttons['Check Attendance']) {
            frm.add_custom_button(__('Check Attendance'), function() {
                frappe.call({
                    method: "hr_vfg.hr_ventureforce_global.custom_events.get_employee_attendance_status",
                    args: {
                        payroll_entry_name: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __("Checking attendance..."),
                    callback: function(r) {
                        if (r.message && r.message.status === "ok") {
                            frm.reload_doc();
                        } else {
                            frappe.msgprint(__("Could not fetch attendance data."));
                        }
                    }
                });
            }, __("Actions"));
        }
        // Add button to create missing advance deductions
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Create Missing Advance Deductions'), function() {
                frappe.call({
                    method: 'hr_vfg.hr_ventureforce_global.custom_events.create_missing_advance_deductions',
                    args: {
                        payroll_entry_name: frm.doc.name
                    },
                    callback: function(r) {
                        if (r.message && r.message.created_records) {
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Create'));
        }
    }
});
