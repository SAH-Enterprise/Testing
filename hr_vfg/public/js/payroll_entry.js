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

function show_gemini_payroll_explanation(frm, explanation, source) {
    const title =
        source === "gemini"
            ? __("Why this failed (Gemini)")
            : __("Why this failed");
    const body = `
        <p>${__("Payroll could not be completed. Explanation below:")}</p>
        <pre style="white-space: pre-wrap; max-height: 320px; overflow: auto; margin: 0;">${frappe.utils.escape_html(
            explanation || ""
        )}</pre>
    `;

    // Same style as desk info / error banners (blue = info)
    frappe.msgprint({
        title: title,
        indicator: "blue",
        message: body,
    });

    frm.set_intro(
        `${__("AI explanation")}: ${(explanation || "").split("\n")[0]}`,
        "blue"
    );
}

function fetch_and_show_gemini_explanation(frm) {
    if (frm.__hr_vfg_gemini_explain_requested) {
        return;
    }
    frm.__hr_vfg_gemini_explain_requested = true;

    frappe.call({
        method: "hr_vfg.hr_ventureforce_global.gemini_explain.explain_payroll_entry_failure",
        args: { payroll_entry_name: frm.doc.name },
        freeze: true,
        freeze_message: __("Asking Gemini why this payroll failed..."),
        callback(r) {
            const data = r.message || {};
            if (!data.explanation) {
                return;
            }
            show_gemini_payroll_explanation(frm, data.explanation, data.source);
        },
        error() {
            frm.__hr_vfg_gemini_explain_requested = false;
        },
    });
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

        frm.add_custom_button(__("Explain with Gemini"), () => {
            frm.__hr_vfg_gemini_explain_requested = false;
            fetch_and_show_gemini_explanation(frm);
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
            label: __("Explain with Gemini"),
            action() {
                frappe.hide_msgprint();
                fetch_and_show_gemini_explanation(frm);
            },
        },
    });

    // Auto-send error to Gemini (or local fallback) and show as info
    fetch_and_show_gemini_explanation(frm);
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

        if (frm.doc.docstatus === 1 && frm.doc.salary_slips_submitted) {
            frm.call('get_accrual_jv_status').then((r) => {
                const status = r.message || {};
                if (status.needs_accrual_jv) {
                    frm.set_intro(
                        __('Accrual Journal Entry is missing or cancelled. Use Actions > Make Accrual Journal Entry before Make Bank Entry.'),
                        'orange'
                    );
                    frm.add_custom_button(__('Make Accrual Journal Entry'), () => {
                        frappe.confirm(
                            __('Create accrual Journal Entry for submitted salary slips?'),
                            () => {
                                frm.call({
                                    doc: frm.doc,
                                    method: 'make_accrual_journal_entry',
                                    freeze: true,
                                    freeze_message: __('Creating accrual Journal Entry...'),
                                    callback: () => frm.reload_doc(),
                                });
                            }
                        );
                    }, __('Actions'));
                } else if (status.active_journal_entries?.length) {
                    frm.add_custom_button(__('View Accrual Journal Entry'), () => {
                        frappe.set_route('Form', 'Journal Entry', status.active_journal_entries[0]);
                    }, __('Actions'));
                }
            });
        }
    }
});
