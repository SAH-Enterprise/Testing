frappe.listview_settings["Meal Form"] = {
	add_fields: [
		"status",
		"per_paid",
		"billed",
		"invoiced",
		"service_billing",
		"purchase_invoice",
		"total_amount",
	],
	get_indicator(doc) {
		const status_colors = {
			Draft: "red",
			"To Bill": "orange",
			Unpaid: "orange",
			"Partly Paid": "yellow",
			Paid: "green",
			Cancelled: "gray",
		};

		const status = doc.status || (cint(doc.docstatus) === 1 ? "To Bill" : "Draft");
		if (status_colors[status]) {
			return [__(status), status_colors[status], "status,=," + status];
		}
	},
};
