# Copyright (c) 2026, VFG and contributors
# License: MIT

"""Explain Payroll Entry failures via Gemini (or a local fallback)."""

from __future__ import annotations

import json
import re
from html import unescape

import frappe
import requests
from frappe import _
from frappe.utils import cstr, strip_html


def _plain_error(html_or_text: str) -> str:
	text = strip_html(cstr(html_or_text or ""))
	return unescape(re.sub(r"\s+", " ", text)).strip()


def _get_gemini_api_key() -> str | None:
	return (
		frappe.conf.get("gemini_api_key")
		or frappe.conf.get("google_gemini_api_key")
		or None
	)


def _build_prompt(payroll_entry: str, company: str, start_date: str, end_date: str, error: str) -> str:
	return "\n".join(
		[
			"You are an ERPNext / HRMS payroll expert.",
			"Explain this Payroll Entry failure in simple language for an accounts/HR user.",
			"Reply in short plain text (no markdown headings).",
			"Cover: (1) what failed, (2) why it happened, (3) exact steps to fix, (4) then retry Submit Salary Slip.",
			"",
			f"Payroll Entry: {payroll_entry}",
			f"Company: {company}",
			f"Period: {start_date} to {end_date}",
			"",
			"Error:",
			error,
		]
	)


def _local_fallback_explanation(error: str) -> str:
	lower = (error or "").lower()

	if "party type and party is required" in lower and "employee advances" in lower:
		return _(
			"Salary Slip submission failed while creating the payroll accrual Journal Entry.\n\n"
			"Why: deduction component Employee Advances - SAH posts to receivable account "
			"Employee Advances - SAH. Receivable/Payable lines need Party Type = Employee and Party.\n\n"
			"These deductions were entered without linking Additional Salary → Employee Advance, "
			"so ERPNext posted one combined Employee Advances line with no employee party.\n\n"
			"Fix applied in system: accrual Journal Entry now posts Employee Advances "
			"employee-wise with Party set.\n"
			"Retry Submit Salary Slip on the Payroll Entry.\n\n"
			"(Local explanation — set site_config gemini_api_key to use Gemini.)"
		)

	if "party type and party is required" in lower and "payroll payable" in lower:
		return _(
			"Salary Slip submission failed while creating the payroll accrual Journal Entry.\n\n"
			"Why: account Payroll Payable - SAH is a Payable account. ERPNext requires "
			"Party Type and Party on that line. Some Salary Components (for example Basic, "
			"House Rent Allowance, Utility) are mapped to Payroll Payable - SAH, so the "
			"Journal Entry starts with that payable account without an employee party.\n\n"
			"Fix:\n"
			"1. Open each Salary Component used in this payroll (Basic, Basic-B, House Rent "
			"Allowance, Utility, Fuel Allowance, Punch Missing, etc.).\n"
			"2. In Accounts table for company SAH ENTERPRISE INC, change the account from "
			"Payroll Payable - SAH to the correct Salary / Expense account "
			"(not Payroll Payable).\n"
			"3. Keep Payroll Payable only on Payroll Entry → Payroll Payable Account.\n"
			"4. Open Payroll Entry again and click Submit Salary Slip.\n\n"
			"(Local explanation — set site_config gemini_api_key to use Gemini.)"
		)

	if "party type and party is required" in lower:
		return _(
			"Journal Entry creation failed because a Receivable/Payable account line has no Party.\n\n"
			"Fix: either set Party Type and Party on that account row, enable "
			"Payroll Settings → Process Payroll Accounting Entry based on Employee, "
			"or change the Salary Component account to a non-party expense/liability account.\n\n"
			"Then retry Submit Salary Slip.\n\n"
			"(Local explanation — set site_config gemini_api_key to use Gemini.)"
		)

	return _(
		"Payroll could not finish because of the error shown above.\n\n"
		"Open Failure Details / Error Log, fix the mentioned master or account setup, "
		"then click Submit Salary Slip again.\n\n"
		"(Local explanation — set site_config gemini_api_key to use Gemini.)"
	)


def _call_gemini(prompt: str) -> str:
	api_key = _get_gemini_api_key()
	if not api_key:
		raise frappe.ValidationError("gemini_api_key_missing")

	model = cstr(frappe.conf.get("gemini_model") or "gemini-2.0-flash")
	url = (
		f"https://generativelanguage.googleapis.com/v1beta/models/"
		f"{model}:generateContent"
	)
	payload = {
		"contents": [{"role": "user", "parts": [{"text": prompt}]}],
		"generationConfig": {
			"temperature": 0.2,
			"maxOutputTokens": 800,
		},
	}
	response = requests.post(
		url,
		params={"key": api_key},
		headers={"Content-Type": "application/json"},
		data=json.dumps(payload),
		timeout=45,
	)
	if response.status_code >= 400:
		frappe.log_error(
			title="Gemini payroll explain failed",
			message=f"HTTP {response.status_code}: {response.text[:2000]}",
		)
		raise frappe.ValidationError(f"gemini_http_{response.status_code}")

	data = response.json()
	parts = (
		(((data.get("candidates") or [{}])[0]).get("content") or {}).get("parts") or []
	)
	text = "\n".join(cstr(p.get("text")) for p in parts if p.get("text")).strip()
	if not text:
		raise frappe.ValidationError("gemini_empty_response")
	return text


@frappe.whitelist()
def explain_payroll_entry_failure(payroll_entry_name: str) -> dict:
	"""Send Payroll Entry error_message to Gemini and return a plain-language explanation."""
	if not payroll_entry_name:
		frappe.throw(_("Payroll Entry is required"))

	doc = frappe.get_doc("Payroll Entry", payroll_entry_name)
	if not doc.has_permission("read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	error = _plain_error(doc.error_message)
	if not error:
		return {
			"source": "none",
			"explanation": _("No failure message found on this Payroll Entry."),
		}

	prompt = _build_prompt(
		payroll_entry=doc.name,
		company=cstr(doc.company),
		start_date=cstr(doc.start_date),
		end_date=cstr(doc.end_date),
		error=error,
	)

	if _get_gemini_api_key():
		try:
			return {"source": "gemini", "explanation": _call_gemini(prompt), "error": error}
		except Exception:
			frappe.log_error(title="Gemini payroll explain exception")

	return {
		"source": "local",
		"explanation": _local_fallback_explanation(error),
		"error": error,
	}
