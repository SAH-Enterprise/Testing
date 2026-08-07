# Copyright (c) 2026, VFG and contributors
# License: MIT

import frappe
from frappe.utils import cint, cstr, get_url, now_datetime
from urllib.parse import quote


def build_punch_payload(log_doc_or_dict):
	"""Build display payload for punch portal from Attendance Logs."""
	if hasattr(log_doc_or_dict, "as_dict") and callable(getattr(log_doc_or_dict, "as_dict", None)):
		log = log_doc_or_dict.as_dict()
	else:
		log = frappe._dict(log_doc_or_dict)

	biometric_id = cstr(log.get("biometric_id")).strip()
	employee_name = ""
	employee = None
	image = ""
	department = ""
	designation = ""

	if biometric_id:
		emp = frappe.db.get_value(
			"Employee",
			{"biometric_id": biometric_id},
			["name", "employee_name", "image", "department", "designation"],
			as_dict=True,
		)
		if emp:
			employee = emp.name
			employee_name = emp.employee_name or emp.name
			image = emp.image or ""
			department = emp.department or ""
			designation = emp.designation or ""

	image_url = ""
	if image:
		if image.startswith("http://") or image.startswith("https://"):
			# Prefer portal proxy for private files so kiosk guests can load photos
			if "/private/files/" in image and biometric_id:
				image_url = (
					"/api/method/hr_vfg.hr_ventureforce_global.punch_portal.get_employee_photo"
					f"?biometric_id={quote(biometric_id)}"
				)
			else:
				image_url = image
		elif image.startswith("/private/files/") and biometric_id:
			image_url = (
				"/api/method/hr_vfg.hr_ventureforce_global.punch_portal.get_employee_photo"
				f"?biometric_id={quote(biometric_id)}"
			)
		else:
			image_url = get_url(image) if not image.startswith("/") else image

	return {
		"name": log.get("name"),
		"biometric_id": biometric_id,
		"employee": employee,
		"employee_name": employee_name or f"ID {biometric_id}" if biometric_id else "Unknown",
		"image": image_url,
		"department": department,
		"designation": designation,
		"attendance_date": cstr(log.get("attendance_date")),
		"attendance_time": cstr(log.get("attendance_time")),
		"type": cstr(log.get("type") or "Punch"),
		"ip": cstr(log.get("ip")),
		"modified": cstr(log.get("modified") or now_datetime()),
	}


def publish_punch_event(log_doc):
	"""Broadcast punch to punch portal clients."""
	try:
		payload = build_punch_payload(log_doc)
		frappe.publish_realtime(
			"attendance_punch",
			payload,
			after_commit=True,
		)
	except Exception:
		frappe.log_error(title="Punch Portal Publish Failed", message=frappe.get_traceback())


def on_attendance_log_insert(doc, method=None):
	publish_punch_event(doc)


TCP_PROBE_CACHE_KEY = "attendance_machine_tcp_probe"


def _probe_machine_tcp(ip, port, timeout=2.0):
	"""Fast TCP reachability check (does not mean full ZK sync succeeded)."""
	import socket

	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock.settimeout(timeout)
	try:
		sock.connect((cstr(ip), int(port)))
		return True, ""
	except Exception as e:
		return False, cstr(e)
	finally:
		try:
			sock.close()
		except Exception:
			pass


def _configured_machines():
	hr_settings = frappe.get_single("V HR Settings")
	configured = []
	for machine in hr_settings.get("attendance_machine") or []:
		if not machine.ip or not machine.port:
			continue
		configured.append(
			{
				"ip": machine.ip,
				"port": str(machine.port),
				"type": machine.type or "Both",
			}
		)
	return configured


@frappe.whitelist(allow_guest=True)
def get_machine_status(force=0):
	"""
	Machine integration status for Punch Portal.

	"Integrated" means ERP successfully connected to the biometric machine on
	the last live sync — not merely that the portal UI refreshed.
	"""
	from hr_vfg.hr_ventureforce_global.doctype.employee_attendance.attendance_connector import (
		MACHINE_STATUS_CACHE_KEY,
	)

	force = cint(force)
	configured = _configured_machines()
	cached = frappe.cache().get_value(MACHINE_STATUS_CACHE_KEY)

	# Prefer last real sync/integration result from attendance connector.
	if cached and not force:
		machines = list(cached.get("machines") or [])
		integrated = bool(cached.get("integrated"))
		partial = bool(cached.get("partial"))
		return {
			"server_time": str(now_datetime()),
			"portal_refreshed_at": str(now_datetime()),
			"machine_checked_at": cached.get("checked_at"),
			"integrated": integrated,
			"partial": partial,
			"online_count": cached.get("online_count", 0),
			"total_count": cached.get("total_count", len(machines)),
			"created_last_sync": cached.get("created", 0),
			"status_label": (
				"Integrated with machines"
				if integrated
				else ("Partially integrated" if partial else "Not integrated with machines")
			),
			"machines": machines,
			"source": "live_sync",
		}

	# TCP probe fallback (cached briefly) — reachable is NOT the same as synced.
	probe = None if force else frappe.cache().get_value(TCP_PROBE_CACHE_KEY)
	if not probe:
		machines = []
		for cfg in configured:
			online, err = _probe_machine_tcp(cfg["ip"], cfg["port"])
			machines.append(
				{
					**cfg,
					"online": online,
					"integrated": False,
					"error": "" if online else (err or "Unreachable"),
					"created": 0,
				}
			)
		online = sum(1 for m in machines if m.get("online"))
		probe = {
			"checked_at": str(now_datetime()),
			"integrated": False,
			"partial": online > 0,
			"online_count": online,
			"total_count": len(machines),
			"created": 0,
			"machines": machines,
			"status_label": (
				"Machines reachable - waiting for sync"
				if online
				else "Not integrated with machines"
			),
		}
		frappe.cache().set_value(TCP_PROBE_CACHE_KEY, probe, expires_in_sec=30)

	return {
		"server_time": str(now_datetime()),
		"portal_refreshed_at": str(now_datetime()),
		"machine_checked_at": probe.get("checked_at"),
		"integrated": False,
		"partial": bool(probe.get("partial")),
		"online_count": probe.get("online_count", 0),
		"total_count": probe.get("total_count", 0),
		"created_last_sync": 0,
		"status_label": probe.get("status_label") or "Not integrated with machines",
		"machines": probe.get("machines") or [],
		"source": "tcp_probe",
	}


@frappe.whitelist(allow_guest=True)
def get_latest_punches(since=None, limit=25):
	"""Return recent Attendance Logs enriched with employee image/name."""
	limit = min(cint(limit) or 25, 50)
	filters = {}
	if since:
		filters["modified"] = [">", since]

	logs = frappe.get_all(
		"Attendance Logs",
		filters=filters,
		fields=[
			"name",
			"biometric_id",
			"attendance_date",
			"attendance_time",
			"type",
			"ip",
			"modified",
			"creation",
		],
		order_by="modified desc",
		limit_page_length=limit,
		ignore_permissions=True,
	)

	# Keep chronological for UI feed (oldest of batch first when rendering new ones)
	logs = list(reversed(logs))
	machine_status = get_machine_status(force=0)
	return {
		"server_time": str(now_datetime()),
		"punches": [build_punch_payload(row) for row in logs],
		"machine_status": machine_status,
	}


@frappe.whitelist(allow_guest=True)
def get_punch_portal_boot():
	return {
		"server_time": str(now_datetime()),
		"title": "Punch Portal",
		"poll_ms": 2000,
	}


@frappe.whitelist(allow_guest=True)
def get_employee_photo(biometric_id=None, employee=None):
	"""Serve employee photo for punch portal (guest-safe)."""
	filters = {}
	if employee:
		filters["name"] = employee
	elif biometric_id:
		filters["biometric_id"] = cstr(biometric_id).strip()
	else:
		frappe.throw("Employee or biometric_id required")

	image = frappe.db.get_value("Employee", filters, "image")
	if not image:
		frappe.throw("No image", frappe.DoesNotExistError)

	file_url = image
	file_doc = frappe.db.get_value(
		"File",
		{"file_url": file_url},
		["name", "file_url", "is_private"],
		as_dict=True,
	)
	if not file_doc and file_url.startswith("/"):
		file_doc = frappe.db.get_value(
			"File",
			{"file_url": file_url},
			["name", "file_url", "is_private"],
			as_dict=True,
		)

	# Redirect/public path if already public
	if file_url.startswith("/files/"):
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = file_url
		return

	from frappe.utils.file_manager import get_file

	try:
		filename, content = get_file(file_url)
	except Exception:
		# Fallback via File doctype
		if not file_doc:
			frappe.throw("File not found", frappe.DoesNotExistError)
		f = frappe.get_doc("File", file_doc.name)
		content = f.get_content()
		filename = f.file_name or "photo.jpg"

	frappe.local.response.filename = filename or "photo.jpg"
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"
