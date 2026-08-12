frappe.ui.form.on("Meal Form", {
	meal_type: function (frm) {
		if (
			frm.doc.meal_type === "Breakfast" ||
			frm.doc.meal_type === "Lunch" ||
			frm.doc.meal_type === "Dinner" ||
			frm.doc.meal_type === "Iftari" ||
			frm.doc.meal_type === "Sehri"
		) {
			frm.toggle_display("detail", true);
			frm.toggle_display("detail_meal", true);
			frm.toggle_display("service_charges_ct", false);
		} else {
			frm.toggle_display("detail", false);
			frm.toggle_display("detail_meal", false);
			frm.toggle_display("service_charges_ct", true);
		}
	},
	refresh: function (frm) {
		frm.trigger("meal_type");
		set_status_indicator(frm);
	},
});

function set_status_indicator(frm) {
	const colors = {
		Draft: "red",
		"To Bill": "orange",
		Unpaid: "orange",
		"Partly Paid": "yellow",
		Paid: "green",
		Cancelled: "gray",
	};
	const status = frm.doc.status || (frm.doc.docstatus === 1 ? "To Bill" : "Draft");
	if (frm.doc.docstatus > 0 || status) {
		frm.page.set_indicator(__(status), colors[status] || "blue");
	}
}
