# Copyright (c) 2026, VFG and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, time_diff_in_hours


DEFAULT_APPROVERS = (
	"Umer",
	"Tahir",
	"Rahil Bhai",
	"Faisal Bhai",
)


class ShortLeaveSettings(Document):
	pass


def get_short_leave_settings():
	return frappe.get_single("Short Leave Settings")


def get_approver_map():
	settings = get_short_leave_settings()
	mapping = {}
	for row in settings.get("short_leave_approvers") or []:
		if row.approver_label and row.user:
			mapping[row.approver_label] = row.user
	return mapping


def ensure_default_approvers():
	"""Seed approver labels on migrate if table is empty."""
	settings = frappe.get_single("Short Leave Settings")
	if settings.get("short_leave_approvers"):
		return
	for label in DEFAULT_APPROVERS:
		user = _find_user_for_label(label)
		settings.append("short_leave_approvers", {"approver_label": label, "user": user or ""})
	settings.flags.ignore_permissions = True
	settings.save()


def _find_user_for_label(label):
	first = (label or "").split()[0]
	for field in ("full_name", "first_name"):
		matches = frappe.get_all(
			"User",
			filters={field: ["like", f"%{first}%"], "enabled": 1},
			pluck="name",
			limit=2,
		)
		if len(matches) == 1:
			return matches[0]
	return None
