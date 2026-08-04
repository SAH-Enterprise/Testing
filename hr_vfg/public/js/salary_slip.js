frappe.ui.form.on("Salary Slip", {
	refresh(frm) {
		if (frm.doc.employee && !frm.doc.custom_grade) {
			fetch_employee_grade(frm);
		}
	},
	employee(frm) {
		fetch_employee_grade(frm);
	},
});

function fetch_employee_grade(frm) {
	if (!frm.doc.employee) {
		frm.set_value("custom_grade", null);
		return;
	}
	frappe.db.get_value("Employee", frm.doc.employee, "custom_employee_grade").then((r) => {
		const grade = r?.message?.custom_employee_grade;
		if (grade && frm.doc.custom_grade !== grade) {
			frm.set_value("custom_grade", grade);
		}
	});
}
