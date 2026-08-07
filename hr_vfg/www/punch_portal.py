import frappe
from frappe.utils import cint, cstr, get_url

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_sidebar = 1
	context.no_header = 1
	context.no_breadcrumbs = 1
	context.title = "Punch Portal"
	context.site_url = get_url()
	return context
