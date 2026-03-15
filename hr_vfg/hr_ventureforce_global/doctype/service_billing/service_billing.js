// Copyright (c) 2026, VFG and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Billing", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button("Fetch Meal Forms", () => {
				if (!frm.doc.from_date || !frm.doc.to_date) {
					frappe.msgprint("Please set From Date and To Date before fetching.");
					return;
				}

				frappe.call({
					method:
						"hr_vfg.hr_ventureforce_global.doctype.service_billing.service_billing.get_meal_forms",
					args: {
						from_date: frm.doc.from_date,
						to_date: frm.doc.to_date,
						meal_type: frm.doc.service_type,
						meal_provider: frm.doc.service_provider,
						contractor: frm.doc.contractor,
					},
					callback: (r) => {
						const data = r.message || {};
						const mealForms = data.meal_forms || [];
						const serviceDetails = data.service_details || [];
						const mealTypeItemMap = data.meal_type_item_map || {};

						frm.clear_table("meal_forms");
						frm.clear_table("service_details");
						if (frm.doc.summary_mode === "Aggregate by Service Type") {
							frm.clear_table("summary");
						}

						mealForms.forEach((row) => {
							const child = frm.add_child("meal_forms");
							child.meal_form = row.name;
							child.date = row.date;
							child.meal_type = row.meal_type;
							child.total_qty = row.total_qty;
							child.total_amount = row.total_amount;
							child.service_qty = row.service_qty;
							child.service_amount = row.service_amount;
							child.contractor_qty = row.total_contractor;
							child.contractor_amount = row.total_contract_amount;
							child.employee_qty = row.total_employees;
							child.employee_amount = row.total_employee_amount;
							child.billed = row.billed;
							child.invoiced = row.invoiced;
						});

						serviceDetails.forEach((row) => {
							const child = frm.add_child("service_details");
							child.meal_form = row.meal_form;
							child.meal_type = row.meal_type;
							child.date = row.date;
							child.item = row.item;
							child.remarks = row.remarks;
							child.qty = row.qty;
							child.amount = row.amount;
						});

						if (frm.doc.summary_mode === "Aggregate by Service Type") {
							const byItem = {};

							mealForms.forEach((row) => {
								const item = mealTypeItemMap[row.meal_type];
								if (!item) return;
								if (!byItem[item]) {
									byItem[item] = { qty: 0, amount: 0 };
								}
								byItem[item].qty += row.total_qty || 0;
								byItem[item].amount += row.total_amount || 0;
							});

							serviceDetails.forEach((row) => {
								const item = row.item;
								if (!item) return;
								if (!byItem[item]) {
									byItem[item] = { qty: 0, amount: 0 };
								}
								byItem[item].qty += row.qty || 0;
								byItem[item].amount += row.amount || 0;
							});

							Object.keys(byItem).forEach((item) => {
								const srow = frm.add_child("summary");
								srow.item = item;
								srow.qty = byItem[item].qty;
								srow.amount = byItem[item].amount;
								srow.rate = byItem[item].qty
									? byItem[item].amount / byItem[item].qty
									: byItem[item].amount;
							});
							frm.refresh_field("summary");
						}

						frm.refresh_field("meal_forms");
						frm.refresh_field("service_details");
						frm.trigger("set_totals");
					},
				});
			});
		}
	},

	set_totals(frm) {
		const totalQty = (frm.doc.meal_forms || []).reduce(
			(sum, row) => sum + (row.total_qty || 0),
			0
		);
		const totalAmount = (frm.doc.meal_forms || []).reduce(
			(sum, row) => sum + (row.total_amount || 0),
			0
		);
		const totalServiceAmount = (frm.doc.service_details || []).reduce(
			(sum, row) => sum + (row.amount || 0),
			0
		);

		frm.set_value("total_qty", totalQty);
		frm.set_value("total_amount", totalAmount);
		frm.set_value("total_service_amount", totalServiceAmount);
	},

	summary_mode(frm) {
		if (frm.doc.summary_mode === "Aggregate by Service Type") {
			frm.clear_table("summary");

			const byItem = {};
			const mealForms = frm.doc.meal_forms || [];
			const serviceDetails = frm.doc.service_details || [];

			const mealTypes = Array.from(
				new Set(mealForms.map((row) => row.meal_type).filter(Boolean))
			);

			if (!mealTypes.length && !serviceDetails.length) {
				frm.refresh_field("summary");
				return;
			}

			const buildSummary = (mealTypeItemMap = {}) => {
				mealForms.forEach((row) => {
					const item = mealTypeItemMap[row.meal_type];
					if (!item) return;
					if (!byItem[item]) {
						byItem[item] = { qty: 0, amount: 0 };
					}
					byItem[item].qty += row.total_qty || 0;
					byItem[item].amount += row.total_amount || 0;
				});

				serviceDetails.forEach((row) => {
					const item = row.item;
					if (!item) return;
					if (!byItem[item]) {
						byItem[item] = { qty: 0, amount: 0 };
					}
					byItem[item].qty += row.qty || 0;
					byItem[item].amount += row.amount || 0;
				});

				Object.keys(byItem).forEach((item) => {
					const srow = frm.add_child("summary");
					srow.item = item;
					srow.qty = byItem[item].qty;
					srow.amount = byItem[item].amount;
					srow.rate = byItem[item].qty
						? byItem[item].amount / byItem[item].qty
						: byItem[item].amount;
				});
				frm.refresh_field("summary");
			};

			if (mealTypes.length) {
				frappe.db
					.get_list("Meal Type", {
						fields: ["name", "item"],
						filters: { name: ["in", mealTypes] },
						limit: 200,
					})
					.then((rows) => {
						const map = {};
						(rows || []).forEach((row) => {
							map[row.name] = row.item;
						});
						buildSummary(map);
					});
			} else {
				buildSummary({});
			}
		}
	},
});

frappe.ui.form.on("Service Billing Meal Form", {
	meal_forms_remove(frm) {
		frm.trigger("set_totals");
	},
});

frappe.ui.form.on("Service Billing Detail", {
	service_details_remove(frm) {
		frm.trigger("set_totals");
	},
});
