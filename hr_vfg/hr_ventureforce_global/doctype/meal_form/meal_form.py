# Copyright (c) 2024, VFG and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt
from datetime import datetime


class MealForm(Document):
	def validate(self):
		self.contract_rate_base_on_category()
		self.employee_rate_base_on_category()
		# self.total_qty_and_total_amount()
		self.total_service_and_total_amount()
		self.total_sum_qty()
		self.total_amount_calculation()
		self.total_contractor_amount()
		self.total_contractor_qty()
		self.total_employee_qty()
		self.total_employee_total()
		self.check_rate_not_zero()
		self.set_status()

	def before_save(self):
		self.total_sum_qty()
		self.total_amount_calculation()
		self.check_rate_not_zero()

	def on_submit(self):
		self.set_status(update=True)

	def on_cancel(self):
		self.db_set({"status": "Cancelled", "per_paid": 0})

	def set_status(self, update=False, update_modified=False):
		"""Same billing/payment status style as Service Billing / Purchase Receipt."""
		if self.docstatus == 0:
			status, per_paid = "Draft", 0
		elif self.docstatus == 2:
			status, per_paid = "Cancelled", 0
		else:
			status, per_paid = self._status_and_percent_from_billing()

		self.status = status
		self.per_paid = per_paid
		if update:
			self.db_set(
				{"status": status, "per_paid": per_paid},
				update_modified=update_modified,
			)

	def _status_and_percent_from_billing(self):
		# Prefer linked Purchase Invoice payment progress
		pi_name = self.purchase_invoice
		sb_name = self.service_billing

		if not pi_name or not sb_name:
			# Repairing/service forms are often only linked via Service Billing Detail
			link = frappe.db.sql(
				"""
				select sb.name as service_billing, sb.purchase_invoice
				from `tabService Billing Detail` sbd
				inner join `tabService Billing` sb on sb.name = sbd.parent
				where sbd.meal_form = %s
					and sbd.parenttype = 'Service Billing'
					and sb.docstatus = 1
				order by sb.modified desc
				limit 1
				""",
				self.name,
				as_dict=True,
			)
			if link:
				if not sb_name:
					sb_name = link[0].service_billing
				if not pi_name:
					pi_name = link[0].purchase_invoice

		if not pi_name and sb_name:
			pi_name = frappe.db.get_value("Service Billing", sb_name, "purchase_invoice")

		if not pi_name:
			# Submitted but not yet billed/invoiced
			return "To Bill", 0

		pi = frappe.db.get_value(
			"Purchase Invoice",
			pi_name,
			["docstatus", "status", "outstanding_amount", "grand_total"],
			as_dict=True,
		)
		if not pi or pi.docstatus == 2:
			return "To Bill", 0

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
		if pi_status in ("Unpaid", "Overdue"):
			return "Unpaid", flt(per_paid, 2)
		if grand_total and outstanding < grand_total:
			return "Partly Paid", flt(per_paid, 2)
		return "Unpaid", flt(per_paid, 2)

	def total_amount_calculation(self):
		# frappe.msgprint('1')
		total_contract_amount = self.total_contract_amount or 0
		total_employee_amount = self.total_employee_amount or 0
		service_amount = self.service_amount or 0
		self.total_amount = total_contract_amount + total_employee_amount + service_amount

	def total_employee_total(self):
		total = 0
		for i in self.detail_meal:
			total += i.amount
		self.total_employee_amount = total

	def total_employee_qty(self):
		qty = 0
		for i in self.detail_meal:
			qty += i.qty
		self.total_employees = qty

	def total_contractor_amount(self):
		total = 0
		for i in self.detail:
			total += i.amount
		self.total_contract_amount = total

	def total_contractor_qty(self):
		qty = 0
		for i in self.detail:
			qty += i.quantity
		self.total_contractor = qty

	def check_rate_not_zero(self):
		invalid_rows = []

		for i in self.detail:
			if flt(i.quantity) > 0 and flt(i.rate) <= 0:
				invalid_rows.append(
					f"Contractor row #{i.idx} (Meal Category: {i.meal_category or 'N/A'})"
				)

		for i in self.detail_meal:
			if flt(i.qty) > 0 and flt(i.rate) <= 0:
				invalid_rows.append(
					f"Employee row #{i.idx} (Meal Category: {i.meal_category or 'N/A'})"
				)

		if invalid_rows:
			frappe.throw("Rate cannot be zero for: " + ", ".join(invalid_rows))

	def total_sum_qty(self):
		contractor_qty = self.total_contractor or 0
		employee_qty = self.total_employees or 0
		service_qty = self.service_qty or 0
		self.total_qty = contractor_qty + employee_qty + service_qty

	def total_service_and_total_amount(self):
		s_qty = 0
		s_amount = 0
		for i in self.service_charges_ct:
			s_qty += i.qty
			s_amount += i.amount
		self.service_qty = s_qty
		self.service_amount = s_amount

	def contract_rate_base_on_category(self):
		meal_provider = frappe.get_doc("Meal Provider", self.meal_provider)
		meal_data = meal_provider.meal_provider_ct

		date = datetime.strptime(self.date, "%Y-%m-%d").date() if isinstance(self.date, str) else self.date

		for j in self.detail:
			matched_rate = self._get_rate_for_row(meal_data, j.meal_category, date)
			if matched_rate is None:
				j.rate = 0
				j.amount = 0
			else:
				j.rate = matched_rate
				j.amount = j.rate * j.quantity

	def employee_rate_base_on_category(self):
		meal_provider = frappe.get_doc("Meal Provider", self.meal_provider)
		meal_data = meal_provider.meal_provider_ct

		date = datetime.strptime(self.date, "%Y-%m-%d").date() if isinstance(self.date, str) else self.date

		for j in self.detail_meal:
			matched_rate = self._get_rate_for_row(meal_data, j.meal_category, date)
			if matched_rate is None:
				j.rate = 0
				j.amount = 0
			else:
				j.rate = matched_rate
				j.amount = j.rate * j.qty

	def _get_rate_for_row(self, meal_data, row_category, date):
		for m in meal_data:
			from_date = datetime.strptime(m.from_date, "%Y-%m-%d").date() if isinstance(m.from_date, str) else m.from_date
			to_date = datetime.strptime(m.to_date, "%Y-%m-%d").date() if isinstance(m.to_date, str) else m.to_date
			if (
				from_date <= date <= to_date
				and m.category == row_category
				and m.meal_type == self.meal_type
			):
				return m.rate
		return None


def update_meal_form_status(meal_form_name, update_modified=False):
	"""Refresh status/% paid for one Meal Form (used by Service Billing / PI hooks)."""
	if not meal_form_name or not frappe.db.exists("Meal Form", meal_form_name):
		return
	doc = frappe.get_doc("Meal Form", meal_form_name)
	doc.set_status(update=True, update_modified=update_modified)


def update_meal_forms_status_from_pi(doc, method=None):
	"""Keep Meal Form status in sync when linked Purchase Invoice changes."""
	names = frappe.get_all(
		"Meal Form",
		filters={"purchase_invoice": doc.name, "docstatus": 1},
		pluck="name",
	)
	# Also via Service Billing link (meal_forms + service_details)
	sb_names = frappe.get_all(
		"Service Billing",
		filters={"purchase_invoice": doc.name},
		pluck="name",
	)
	for sb in sb_names:
		for mf in frappe.get_all(
			"Service Billing Meal Form",
			filters={"parent": sb, "parenttype": "Service Billing"},
			pluck="meal_form",
		):
			if mf and mf not in names:
				names.append(mf)
		if frappe.db.has_column("Service Billing Detail", "meal_form"):
			for mf in frappe.get_all(
				"Service Billing Detail",
				filters={"parent": sb, "parenttype": "Service Billing"},
				pluck="meal_form",
			):
				if mf and mf not in names:
					names.append(mf)

	for name in names:
		update_meal_form_status(name)
