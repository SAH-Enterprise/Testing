from frappe import _


def get_meal_form_dashboard_data(data=None):
	data = data or {}
	transactions = data.get("transactions", [])
	transactions.append(
		{"label": _("Billing"), "items": ["Service Billing", "Purchase Invoice"]}
	)
	data["transactions"] = transactions
	data.setdefault("fieldname", "meal_form")
	data.setdefault("internal_links", {})
	data["internal_links"].update(
		{
			"Service Billing": "service_billing",
			"Purchase Invoice": "purchase_invoice",
		}
	)
	return data


def get_service_billing_dashboard_data(data=None):
	data = data or {}
	transactions = data.get("transactions", [])
	transactions.append(
		{"label": _("References"), "items": ["Meal Form", "Purchase Invoice"]}
	)
	data["transactions"] = transactions
	data.setdefault("fieldname", "service_billing")
	data.setdefault("internal_links", {})
	data["internal_links"].update(
		{
			"Meal Form": ["meal_forms", "meal_form"],
			"Purchase Invoice": "purchase_invoice",
		}
	)
	return data


def get_purchase_invoice_dashboard_data(data=None):
	data = data or {}
	transactions = data.get("transactions", [])
	transactions.append(
		{"label": _("Service Billing"), "items": ["Service Billing", "Meal Form"]}
	)
	data["transactions"] = transactions
	data.setdefault("fieldname", "purchase_invoice")
	return data
