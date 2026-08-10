# Copyright (c) 2026, VFG and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ServiceBilling(Document):
	def validate(self):
		self._validate_dates()
		self._set_supplier()
		self._set_totals()
		self.set_status()

	def on_submit(self):
		self._mark_meal_forms_billed()
		self._create_purchase_invoice()
		self.set_status(update=True)

	def before_cancel(self):
		self._validate_linked_purchase_invoice_before_remove(_("cancel"))

	def on_cancel(self):
		self._unmark_meal_forms()
		self.db_set("status", "Cancelled")
		self.db_set("per_paid", 0)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw(_("Submitted Service Billing cannot be deleted. Cancel it first."))
		self._validate_linked_purchase_invoice_before_remove(_("delete"))
		self._unmark_meal_forms()

	def _validate_dates(self):
		if self.from_date and self.to_date and self.from_date > self.to_date:
			frappe.throw(_("From Date cannot be after To Date."))

	def _set_totals(self):
		self.total_qty = sum(flt(row.total_qty) for row in self.meal_forms)
		self.total_amount = sum(flt(row.total_amount) for row in self.meal_forms)
		self.total_service_amount = sum(flt(row.amount) for row in self.service_details)

	def _set_supplier(self):
		if not self.service_provider:
			self.supplier = None
			return
		self.supplier = frappe.db.get_value("Meal Provider", self.service_provider, "supplier")

	def set_status(self, update=False, update_modified=False):
		"""Mirror billing/payment progress like Purchase Receipt / Purchase Invoice."""
		if self.docstatus == 0:
			status = "Draft"
			per_paid = 0
		elif self.docstatus == 2:
			status = "Cancelled"
			per_paid = 0
		else:
			status, per_paid = self._status_and_percent_from_purchase_invoice()

		self.status = status
		self.per_paid = per_paid
		if update:
			self.db_set(
				{"status": status, "per_paid": per_paid},
				update_modified=update_modified,
			)

	def _status_and_percent_from_purchase_invoice(self):
		if not self.purchase_invoice:
			return "To Bill", 0

		pi = frappe.db.get_value(
			"Purchase Invoice",
			self.purchase_invoice,
			["docstatus", "status", "outstanding_amount", "grand_total", "paid_amount"],
			as_dict=True,
		)
		if not pi or pi.docstatus == 2:
			return "To Bill", 0

		# Draft PI created from Service Billing — still pending billing/payment
		if pi.docstatus == 0:
			return "To Bill", 0

		grand_total = flt(pi.grand_total)
		outstanding = flt(pi.outstanding_amount)
		if grand_total > 0:
			per_paid = max(0, min(100, ((grand_total - outstanding) / grand_total) * 100))
		else:
			per_paid = 100 if outstanding <= 0 else 0

		pi_status = (pi.status or "").strip()
		if pi_status == "Paid" or (grand_total and outstanding <= 0):
			return "Paid", 100
		if pi_status == "Partly Paid" or (grand_total and 0 < outstanding < grand_total):
			return "Partly Paid", flt(per_paid, 2)
		if pi_status == "Overdue":
			return "Unpaid", flt(per_paid, 2)
		if pi_status == "Unpaid":
			return "Unpaid", flt(per_paid, 2)

		if grand_total and outstanding < grand_total:
			return "Partly Paid", flt(per_paid, 2)
		return "Unpaid", flt(per_paid, 2)

	def _validate_linked_purchase_invoice_before_remove(self, action):
		"""Do not allow cancel/delete of Service Billing while linked PI still exists."""
		if not self.purchase_invoice:
			return

		if not frappe.db.exists("Purchase Invoice", self.purchase_invoice):
			return

		pi_docstatus = frappe.db.get_value("Purchase Invoice", self.purchase_invoice, "docstatus")
		if pi_docstatus == 2:
			return

		frappe.throw(
			_(
				"Cannot {0} Service Billing {1} because Purchase Invoice {2} still exists. "
				"Cancel or delete the Purchase Invoice first."
			).format(action, self.name, frappe.bold(self.purchase_invoice)),
			title=_("Linked Purchase Invoice"),
		)

	def _mark_meal_forms_billed(self):
		for row in self.meal_forms:
			if not row.meal_form:
				continue
			frappe.db.set_value(
				"Meal Form",
				row.meal_form,
				{
					"billed": 1,
					"service_billing": self.name,
				},
			)

	def _unmark_meal_forms(self):
		for row in self.meal_forms:
			if not row.meal_form:
				continue
			values = {
				"billed": 0,
				"service_billing": None,
			}
			if frappe.db.has_column("Meal Form", "invoiced"):
				values.update(
					{
						"invoiced": 0,
						"invoiced_amount": 0,
						"purchase_invoice": None,
					}
				)
			frappe.db.set_value("Meal Form", row.meal_form, values)

	def _create_purchase_invoice(self):
		if self.purchase_invoice:
			return

		if not self.service_provider:
			frappe.throw(_("Service Provider is required to create Purchase Invoice."))

		supplier = frappe.db.get_value("Meal Provider", self.service_provider, "supplier")
		if not supplier:
			frappe.throw(_("Supplier is not set in the selected Service Provider."))

		company = (
			frappe.defaults.get_user_default("Company")
			or frappe.db.get_single_value("Global Defaults", "default_company")
		)
		if not company:
			frappe.throw(_("Default Company is not set."))

		company_cost_center = frappe.db.get_value("Company", company, "cost_center")
		service_type_cost_center = None
		if self.service_type and frappe.db.has_column("Meal Type", "cost_center"):
			service_type_cost_center = frappe.db.get_value(
				"Meal Type",
				self.service_type,
				"cost_center",
			)

		supplier_invoice_no = getattr(self, "supplier_invoice_no", None)
		supplier_invoice_date = getattr(self, "supplier_invoice_date", None)
		if not supplier_invoice_no or not supplier_invoice_date:
			frappe.throw(_("Supplier Invoice No and Supplier Invoice Date are required."))

		if self.summary:
			pi = frappe.new_doc("Purchase Invoice")
			pi.supplier = supplier
			pi.company = company
			pi.posting_date = self.posting_date
			pi.posting_time = self.posting_time
			pi.naming_series = "PINV-LOCAL-.###.-.YY."
			pi.bill_no = supplier_invoice_no
			pi.bill_date = supplier_invoice_date

			for row in self.summary:
				if not row.item:
					continue
				qty = flt(row.qty) or 1
				amount = flt(row.amount)
				rate = flt(row.rate)
				if not rate and amount and qty:
					rate = amount / qty
				if not amount and rate and qty:
					amount = rate * qty
				self._append_pi_item(
					pi,
					row.item,
					qty,
					rate or amount,
					company_cost_center,
					service_type_cost_center,
					company,
					row.cost_center,
				)

			self._finalize_purchase_invoice(pi, supplier)
			return

		if not self.service_details:
			pi = frappe.new_doc("Purchase Invoice")
			pi.supplier = supplier
			pi.company = company
			pi.posting_date = self.posting_date
			pi.posting_time = self.posting_time
			pi.naming_series = "PINV-LOCAL-.###.-.YY."
			pi.bill_no = supplier_invoice_no
			pi.bill_date = supplier_invoice_date

			item = None
			if self.service_type:
				item = frappe.db.get_value("Meal Type", self.service_type, "item")
			if not item:
				frappe.throw(_("Service Detail rows are required or set Item on Meal Type."))

			qty = flt(self.total_qty) or 1
			amount = flt(self.total_amount)
			rate = amount / qty if qty else amount

			self._append_pi_item(
				pi,
				item,
				qty,
				rate,
				company_cost_center,
				service_type_cost_center,
				company,
			)
			self._finalize_purchase_invoice(pi, supplier)
			return

		pi = frappe.new_doc("Purchase Invoice")
		pi.supplier = supplier
		pi.company = company
		pi.posting_date = self.posting_date
		pi.posting_time = self.posting_time
		pi.naming_series = "PINV-LOCAL-.###.-.YY."
		pi.bill_no = supplier_invoice_no
		pi.bill_date = supplier_invoice_date

		for row in self.service_details:
			if not row.item:
				continue
			qty = flt(row.qty) or 1
			amount = flt(row.amount)
			rate = amount / qty if qty else amount
			self._append_pi_item(
				pi,
				row.item,
				qty,
				rate,
				company_cost_center,
				service_type_cost_center,
				company,
			)

		self._finalize_purchase_invoice(pi, supplier)

	def _append_pi_item(
		self,
		pi,
		item,
		qty,
		rate,
		company_cost_center=None,
		service_type_cost_center=None,
		company=None,
		row_cost_center=None,
	):
		cost_center = row_cost_center or service_type_cost_center or company_cost_center
		if not cost_center and company:
			cost_center = frappe.db.get_value(
				"Item Default",
				{"parent": item, "company": company},
				"buying_cost_center",
			)
		if not cost_center:
			frappe.throw(
				_(
					"Cost Center is required. Set Service Type Cost Center, Company Cost Center, or Item Default Buying Cost Center."
				)
			)
		pi.append(
			"items",
			{
				"item_code": item,
				"qty": qty,
				"rate": rate,
				"cost_center": cost_center,
			},
		)

	def _finalize_purchase_invoice(self, pi, supplier):
		# Keep related PI under the Service Billing owner (creator),
		# even when another user (e.g. Administrator) submits the billing.
		source_owner = self.owner or frappe.session.user
		pi.owner = source_owner
		pi.insert(ignore_permissions=True)
		if pi.owner != source_owner:
			frappe.db.set_value(
				"Purchase Invoice", pi.name, "owner", source_owner, update_modified=False
			)
			pi.owner = source_owner

		# pi.submit()

		if source_owner and source_owner not in ("Administrator", "Guest"):
			frappe.share.add_docshare(
				"Purchase Invoice",
				pi.name,
				source_owner,
				read=1,
				write=1,
				submit=0,
				share=0,
				flags={"ignore_share_permission": True},
			)

		self.db_set("purchase_invoice", pi.name)
		self.purchase_invoice = pi.name
		self.db_set("supplier", supplier)

		for row in self.meal_forms:
			if not row.meal_form:
				continue
			frappe.db.set_value(
				"Meal Form",
				row.meal_form,
				{
					"invoiced": 1,
					"invoiced_amount": flt(row.total_amount),
					"purchase_invoice": pi.name,
				},
			)


def update_service_billing_status_from_pi(doc, method=None):
	"""Keep Service Billing status in sync when Purchase Invoice changes."""
	sb_name = frappe.db.get_value("Service Billing", {"purchase_invoice": doc.name}, "name")
	if not sb_name:
		return

	sb = frappe.get_doc("Service Billing", sb_name)
	if sb.docstatus != 1:
		return
	sb.set_status(update=True)


def clear_service_billing_link_on_pi_cancel(doc, method=None):
	"""When PI is cancelled/deleted, free the Service Billing link and reset meal form invoice flags."""
	sb_name = frappe.db.get_value("Service Billing", {"purchase_invoice": doc.name}, "name")
	if not sb_name:
		return

	sb = frappe.get_doc("Service Billing", sb_name)
	frappe.db.set_value("Service Billing", sb_name, "purchase_invoice", None, update_modified=False)

	for row in sb.meal_forms:
		if not row.meal_form:
			continue
		values = {}
		if frappe.db.has_column("Meal Form", "invoiced"):
			values.update(
				{
					"invoiced": 0,
					"invoiced_amount": 0,
					"purchase_invoice": None,
				}
			)
		if values:
			frappe.db.set_value("Meal Form", row.meal_form, values)

	# Reload link cleared for status calc
	sb.purchase_invoice = None
	if sb.docstatus == 1:
		sb.set_status(update=True)
	elif sb.docstatus == 2:
		frappe.db.set_value(
			"Service Billing",
			sb_name,
			{"status": "Cancelled", "per_paid": 0},
			update_modified=False,
		)


@frappe.whitelist()
def get_meal_forms(from_date, to_date, meal_type=None, meal_provider=None, contractor=None):
	if not from_date or not to_date:
		frappe.throw(_("From Date and To Date are required."))

	has_billed = frappe.db.has_column("Meal Form", "billed")
	has_invoiced = frappe.db.has_column("Meal Form", "invoiced")

	if contractor:
		conditions = ["mf.docstatus = 1", "mf.date between %s and %s"]
		values = [from_date, to_date]

		if meal_type:
			conditions.append("mf.meal_type = %s")
			values.append(meal_type)
		if meal_provider:
			conditions.append("mf.meal_provider = %s")
			values.append(meal_provider)
		if has_billed:
			conditions.append("ifnull(mf.billed, 0) = 0")
		if has_invoiced:
			conditions.append("ifnull(mf.invoiced, 0) = 0")

		conditions.append("d.contractor = %s")
		values.append(contractor)

		meal_form_names = frappe.db.sql(
			f"""
			select distinct mf.name
			from `tabMeal Form` mf
			inner join `tabDetail` d
				on d.parent = mf.name
				and d.parenttype = 'Meal Form'
				and d.parentfield = 'detail'
			where {' and '.join(conditions)}
			""",
			values,
			as_list=True,
		)
		meal_form_names = [row[0] for row in meal_form_names]
	else:
		filters = {
			"docstatus": 1,
			"date": ["between", [from_date, to_date]],
		}
		if meal_type:
			filters["meal_type"] = meal_type
		if meal_provider:
			filters["meal_provider"] = meal_provider
		if has_billed:
			filters["billed"] = 0
		if has_invoiced:
			filters["invoiced"] = 0

		meal_form_names = frappe.get_all("Meal Form", filters=filters, pluck="name")

	if not meal_form_names:
		return {"meal_forms": [], "service_details": [], "meal_type_item_map": {}}

	meal_forms = frappe.get_all(
		"Meal Form",
		filters={"name": ["in", meal_form_names]},
		fields=[
			"name",
			"date",
			"meal_type",
			"total_qty",
			"total_amount",
			"service_qty",
			"service_amount",
			"total_contractor",
			"total_contract_amount",
			"total_employees",
			"total_employee_amount",
			"remarks",
			"billed",
			"invoiced",
		],
		order_by="date asc",
	)

	service_details = frappe.get_all(
		"Service Charges CT",
		filters={
			"parent": ["in", meal_form_names],
			"parenttype": "Meal Form",
		},
		fields=[
			"parent as meal_form",
			"item",
			"remarks",
			"qty",
			"amount",
		],
		order_by="parent asc",
	)
	meal_form_meta = {
		row.get("name"): {"meal_type": row.get("meal_type"), "date": row.get("date")}
		for row in meal_forms
	}
	for row in service_details:
		meta = meal_form_meta.get(row.get("meal_form")) or {}
		row["meal_type"] = meta.get("meal_type")
		row["date"] = meta.get("date")

	meal_type_map = {}
	if meal_forms:
		meal_types = list({row.get("meal_type") for row in meal_forms if row.get("meal_type")})
		if meal_types:
			for row in frappe.get_all(
				"Meal Type",
				filters={"name": ["in", meal_types]},
				fields=["name", "item"],
			):
				meal_type_map[row.name] = row.item

	allowed_meal_types = {"Lunch", "Dinner", "Breakfast", "Sehri", "Iftari"}
	filtered_meal_forms = []
	extra_service_details = []
	non_allowed_meal_forms = set()
	for row in meal_forms:
		if row.get("meal_type") in allowed_meal_types:
			filtered_meal_forms.append(row)
		else:
			non_allowed_meal_forms.add(row.get("name"))
			item = meal_type_map.get(row.get("meal_type"))
			if item:
				extra_service_details.append(
					{
						"meal_form": row.get("name"),
						"meal_type": row.get("meal_type"),
						"date": row.get("date"),
						"item": item,
						"remarks": f"From Meal Form ({row.get('meal_type')})",
						"qty": row.get("total_qty"),
						"amount": row.get("total_amount"),
					}
				)

	return {
		"meal_forms": filtered_meal_forms,
		# Keep all actual Service Charges CT rows; for non-standard meal types also append
		# an aggregate line derived from Meal Form totals.
		"service_details": service_details + extra_service_details,
		"meal_type_item_map": meal_type_map,
	}
