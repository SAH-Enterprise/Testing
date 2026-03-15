import frappe
from frappe.utils import add_days, nowdate


def _date_group_expr(fieldname, granularity):
	if granularity == "Weekly":
		return f"date_format({fieldname}, '%%x-%%v')"
	if granularity == "Monthly":
		return f"date_format({fieldname}, '%%Y-%%m-01')"
	return fieldname


def _get_meal_form_names(from_date, to_date, meal_type=None, meal_provider=None, contractor=None, billed=None, invoiced=None):
	conditions = ["mf.docstatus = 1", "mf.date between %s and %s"]
	values = [from_date, to_date]

	if meal_type:
		conditions.append("mf.meal_type = %s")
		values.append(meal_type)
	if meal_provider:
		conditions.append("mf.meal_provider = %s")
		values.append(meal_provider)
	if billed == "Billed":
		conditions.append("ifnull(mf.billed, 0) = 1")
	elif billed == "Not Billed":
		conditions.append("ifnull(mf.billed, 0) = 0")
	if invoiced == "Invoiced":
		conditions.append("ifnull(mf.invoiced, 0) = 1")
	elif invoiced == "Not Invoiced":
		conditions.append("ifnull(mf.invoiced, 0) = 0")

	if contractor:
		conditions.append(
			"""
			exists (
				select 1 from `tabDetail` d
				where d.parent = mf.name
				and d.parenttype = 'Meal Form'
				and d.parentfield = 'detail'
				and d.contractor = %s
			)
			"""
		)
		values.append(contractor)

	meal_form_names = frappe.db.sql(
		f"""
		select mf.name
		from `tabMeal Form` mf
		where {' and '.join(conditions)}
		""",
		values,
		as_list=True,
	)
	return [row[0] for row in meal_form_names]


@frappe.whitelist()
def get_dashboard_data(
	from_date=None,
	to_date=None,
	service_provider=None,
	contractor=None,
	service_type=None,
	meal_provider=None,
	billed=None,
	invoiced=None,
	granularity="Daily",
):
	if not to_date:
		to_date = nowdate()
	if not from_date:
		from_date = add_days(to_date, -30)

	meal_form_names = _get_meal_form_names(
		from_date, to_date, service_type, meal_provider, contractor, billed, invoiced
	)

	# Service Billing
	sb_conditions = ["docstatus = 1", "posting_date between %s and %s"]
	sb_values = [from_date, to_date]
	if service_provider:
		sb_conditions.append("service_provider = %s")
		sb_values.append(service_provider)
	if contractor:
		sb_conditions.append("contractor = %s")
		sb_values.append(contractor)
	if service_type:
		sb_conditions.append("service_type = %s")
		sb_values.append(service_type)
	if invoiced == "Invoiced":
		sb_conditions.append("purchase_invoice is not null and purchase_invoice != ''")
	elif invoiced == "Not Invoiced":
		sb_conditions.append("(purchase_invoice is null or purchase_invoice = '')")

	service_billing_stats = frappe.db.sql(
		f"""
		select
			count(name) as total_bills,
			sum(total_amount) as total_amount,
			sum(total_service_amount) as total_service_amount,
			sum(total_qty) as total_qty,
			sum(case when purchase_invoice is not null and purchase_invoice != '' then 1 else 0 end) as invoiced_count
		from `tabService Billing`
		where {' and '.join(sb_conditions)}
		""",
		sb_values,
		as_dict=True,
	)[0]

	sb_group = _date_group_expr("posting_date", granularity)
	service_billing_trend = frappe.db.sql(
		f"""
		select {sb_group} as date, sum(total_amount) as amount
		from `tabService Billing`
		where {' and '.join(sb_conditions)}
		group by {sb_group}
		order by {sb_group} asc
		""",
		sb_values,
		as_dict=True,
	)
	service_billing_qty_trend = frappe.db.sql(
		f"""
		select {sb_group} as date, sum(total_qty) as qty
		from `tabService Billing`
		where {' and '.join(sb_conditions)}
		group by {sb_group}
		order by {sb_group} asc
		""",
		sb_values,
		as_dict=True,
	)
	service_billing_avg_rate_trend = frappe.db.sql(
		f"""
		select {sb_group} as date,
			   sum(total_amount) / nullif(sum(total_qty), 0) as avg_rate
		from `tabService Billing`
		where {' and '.join(sb_conditions)}
		group by {sb_group}
		order by {sb_group} asc
		""",
		sb_values,
		as_dict=True,
	)

	# Meal Form
	meal_form_stats = {"total_forms": 0, "total_amount": 0, "total_qty": 0}
	meal_form_trend = []
	meal_form_qty_trend = []
	meal_form_by_type = []
	if meal_form_names:
		meal_form_stats = frappe.db.sql(
			"""
			select
				count(name) as total_forms,
				sum(total_amount) as total_amount,
				sum(total_qty) as total_qty
			from `tabMeal Form`
			where name in %(names)s
			""",
			{"names": meal_form_names},
			as_dict=True,
		)[0]

		mf_group = _date_group_expr("date", granularity)
		meal_form_trend = frappe.db.sql(
			f"""
			select {mf_group} as date, sum(total_amount) as amount
			from `tabMeal Form`
			where name in %(names)s
			group by {mf_group}
			order by {mf_group} asc
			""",
			{"names": meal_form_names},
			as_dict=True,
		)
		meal_form_qty_trend = frappe.db.sql(
			f"""
			select {mf_group} as date, sum(total_qty) as qty
			from `tabMeal Form`
			where name in %(names)s
			group by {mf_group}
			order by {mf_group} asc
			""",
			{"names": meal_form_names},
			as_dict=True,
		)

		meal_form_by_type = frappe.db.sql(
			"""
			select meal_type, sum(total_amount) as amount, sum(total_qty) as qty
			from `tabMeal Form`
			where name in %(names)s
			group by meal_type
			order by amount desc
			""",
			{"names": meal_form_names},
			as_dict=True,
		)

	# Service Detail (from Service Charges CT)
	service_detail_trend = []
	service_detail_qty_trend = []
	service_detail_by_item = []
	service_detail_list = []
	if meal_form_names:
		sd_group = _date_group_expr("mf.date", granularity)
		service_detail_trend = frappe.db.sql(
			f"""
			select {sd_group} as date, sum(sd.amount) as amount
			from `tabService Charges CT` sd
			inner join `tabMeal Form` mf on mf.name = sd.parent
			where sd.parenttype = 'Meal Form'
			and mf.name in %(names)s
			group by {sd_group}
			order by {sd_group} asc
			""",
			{"names": meal_form_names},
			as_dict=True,
		)
		service_detail_qty_trend = frappe.db.sql(
			f"""
			select {sd_group} as date, sum(sd.qty) as qty
			from `tabService Charges CT` sd
			inner join `tabMeal Form` mf on mf.name = sd.parent
			where sd.parenttype = 'Meal Form'
			and mf.name in %(names)s
			group by {sd_group}
			order by {sd_group} asc
			""",
			{"names": meal_form_names},
			as_dict=True,
		)

		service_detail_by_item = frappe.db.sql(
			"""
			select sd.item, sum(sd.amount) as amount, sum(sd.qty) as qty
			from `tabService Charges CT` sd
			where sd.parenttype = 'Meal Form'
			and sd.parent in %(names)s
			group by sd.item
			order by amount desc
			""",
			{"names": meal_form_names},
			as_dict=True,
		)

		service_detail_list = frappe.db.sql(
			"""
			select
				sd.parent as meal_form,
				mf.meal_type,
				mf.date,
				sd.item,
				sd.qty,
				sd.amount,
				sd.remarks
			from `tabService Charges CT` sd
			inner join `tabMeal Form` mf on mf.name = sd.parent
			where sd.parenttype = 'Meal Form'
			and sd.parent in %(names)s
			order by mf.date desc
			limit 20
			""",
			{"names": meal_form_names},
			as_dict=True,
		)

	# Top lists
	top_providers = frappe.db.sql(
		f"""
		select service_provider, sum(total_amount) as amount
		from `tabService Billing`
		where {' and '.join(sb_conditions)}
		group by service_provider
		order by amount desc
		limit 10
		""",
		sb_values,
		as_dict=True,
	)

	top_contractors = frappe.db.sql(
		f"""
		select contractor, sum(total_amount) as amount
		from `tabService Billing`
		where {' and '.join(sb_conditions)}
		group by contractor
		order by amount desc
		limit 10
		""",
		sb_values,
		as_dict=True,
	)

	provider_by_type = []
	contractor_by_type = []
	if meal_form_names:
		provider_by_type = frappe.db.sql(
			"""
			select meal_provider as service_provider, meal_type as service_type, sum(total_amount) as amount
			from `tabMeal Form`
			where name in %(names)s
			group by meal_provider, meal_type
			""",
			{"names": meal_form_names},
			as_dict=True,
		)

		contractor_by_type = frappe.db.sql(
			"""
			select d.contractor as contractor, mf.meal_type as service_type, sum(d.amount) as amount
			from `tabDetail` d
			inner join `tabMeal Form` mf on mf.name = d.parent
			where d.parenttype = 'Meal Form'
			and d.parentfield = 'detail'
			and mf.name in %(names)s
			group by d.contractor, mf.meal_type
			""",
			{"names": meal_form_names},
			as_dict=True,
		)

	meal_provider_amount = []
	if meal_form_names:
		meal_provider_amount = frappe.db.sql(
			"""
			select meal_provider, sum(total_amount) as amount
			from `tabMeal Form`
			where name in %(names)s
			group by meal_provider
			order by amount desc
			""",
			{"names": meal_form_names},
			as_dict=True,
		)

	department_amount = []
	if meal_form_names:
		department_amount = frappe.db.sql(
			"""
			select dm.department, sum(dm.amount) as amount
			from `tabDetail Meal` dm
			where dm.parenttype = 'Meal Form'
			and dm.parent in %(names)s
			group by dm.department
			order by amount desc
			""",
			{"names": meal_form_names},
			as_dict=True,
		)

	sb_conditions_alias = [
		("sb." + cond) if cond.startswith("docstatus") else cond for cond in sb_conditions
	]
	cost_center_amount = frappe.db.sql(
		f"""
		select sbs.cost_center, sum(sbs.amount) as amount
		from `tabService Billing Summary` sbs
		inner join `tabService Billing` sb on sb.name = sbs.parent
		where {' and '.join(sb_conditions_alias)}
		group by sbs.cost_center
		order by amount desc
		""",
		sb_values,
		as_dict=True,
	)

	# Scatter data
	meal_form_scatter = []
	if meal_form_names:
		meal_form_scatter = frappe.db.sql(
			"""
			select name, total_qty as x, total_amount as y
			from `tabMeal Form`
			where name in %(names)s
			order by date desc
			limit 50
			""",
			{"names": meal_form_names},
			as_dict=True,
		)

	# Billed/Invoiced splits
	billed_split = {"billed": 0, "not_billed": 0}
	if meal_form_names:
		billed_split = frappe.db.sql(
			"""
			select
				sum(case when ifnull(billed, 0) = 1 then 1 else 0 end) as billed,
				sum(case when ifnull(billed, 0) = 0 then 1 else 0 end) as not_billed
			from `tabMeal Form`
			where name in %(names)s
			""",
			{"names": meal_form_names},
			as_dict=True,
		)[0]

	invoiced_split = frappe.db.sql(
		f"""
		select
			sum(case when purchase_invoice is not null and purchase_invoice != '' then 1 else 0 end) as invoiced,
			sum(case when purchase_invoice is null or purchase_invoice = '' then 1 else 0 end) as not_invoiced
		from `tabService Billing`
		where {' and '.join(sb_conditions)}
		""",
		sb_values,
		as_dict=True,
	)[0]

	# Purchase Invoice trends
	sb_group_pi = _date_group_expr("sb.posting_date", granularity)
	sb_conditions_pi = []
	for cond in sb_conditions:
		if cond.startswith("docstatus"):
			sb_conditions_pi.append("sb." + cond)
		elif cond.startswith("posting_date"):
			sb_conditions_pi.append("sb." + cond)
		else:
			sb_conditions_pi.append(cond)
	pi_amount_trend = frappe.db.sql(
		f"""
		select {sb_group_pi} as date, sum(pi.grand_total) as amount
		from `tabService Billing` sb
		inner join `tabPurchase Invoice` pi on pi.name = sb.purchase_invoice
		where {' and '.join(sb_conditions_pi)} and pi.docstatus = 1
		group by {sb_group_pi}
		order by {sb_group_pi} asc
		""",
		sb_values,
		as_dict=True,
	)

	pi_avg_trend = frappe.db.sql(
		f"""
		select {sb_group_pi} as date, avg(pi.grand_total) as avg_amount
		from `tabService Billing` sb
		inner join `tabPurchase Invoice` pi on pi.name = sb.purchase_invoice
		where {' and '.join(sb_conditions_pi)} and pi.docstatus = 1
		group by {sb_group_pi}
		order by {sb_group_pi} asc
		""",
		sb_values,
		as_dict=True,
	)

	# Day of week counts
	sb_by_day = frappe.db.sql(
		f"""
		select dayname(posting_date) as day, count(name) as count
		from `tabService Billing`
		where {' and '.join(sb_conditions)}
		group by dayname(posting_date)
		""",
		sb_values,
		as_dict=True,
	)

	mf_by_day = []
	if meal_form_names:
		mf_by_day = frappe.db.sql(
			"""
			select dayname(date) as day, count(name) as count
			from `tabMeal Form`
			where name in %(names)s
			group by dayname(date)
			""",
			{"names": meal_form_names},
			as_dict=True,
		)

	# Lead time buckets
	lead_time_buckets = {"0": 0, "1": 0, "2": 0, "3-5": 0, "6-10": 0, "10+": 0}
	lead_times = frappe.db.sql(
		f"""
		select datediff(sb.posting_date, mf.date) as diff
		from `tabService Billing Meal Form` sbmf
		inner join `tabService Billing` sb on sb.name = sbmf.parent
		inner join `tabMeal Form` mf on mf.name = sbmf.meal_form
		where {' and '.join(sb_conditions_pi)}
		""",
		sb_values,
		as_dict=True,
	)
	for row in lead_times:
		diff = row.get("diff")
		if diff is None:
			continue
		if diff <= 0:
			lead_time_buckets["0"] += 1
		elif diff == 1:
			lead_time_buckets["1"] += 1
		elif diff == 2:
			lead_time_buckets["2"] += 1
		elif 3 <= diff <= 5:
			lead_time_buckets["3-5"] += 1
		elif 6 <= diff <= 10:
			lead_time_buckets["6-10"] += 1
		else:
			lead_time_buckets["10+"] += 1

	# Lists
	service_billing_list = frappe.db.sql(
		f"""
		select name, posting_date, service_provider, service_type, contractor,
			   total_qty, total_amount, total_service_amount, purchase_invoice
		from `tabService Billing`
		where {' and '.join(sb_conditions)}
		order by posting_date desc
		limit 20
		""",
		sb_values,
		as_dict=True,
	)

	meal_form_list = []
	if meal_form_names:
		meal_form_list = frappe.db.sql(
			"""
			select name, date, meal_type, meal_provider, total_qty, total_amount, billed, invoiced
			from `tabMeal Form`
			where name in %(names)s
			order by date desc
			limit 20
			""",
			{"names": meal_form_names},
			as_dict=True,
		)

	summary_list = []
	if service_billing_list:
		sb_names = [row["name"] for row in service_billing_list]
		summary_list = frappe.db.sql(
			"""
			select parent as service_billing, item, qty, rate, amount, cost_center
			from `tabService Billing Summary`
			where parent in %(names)s
			order by modified desc
			limit 20
			""",
			{"names": sb_names},
			as_dict=True,
		)

	return {
		"from_date": from_date,
		"to_date": to_date,
		"granularity": granularity,
		"service_billing_stats": service_billing_stats,
		"service_billing_trend": service_billing_trend,
		"service_billing_qty_trend": service_billing_qty_trend,
		"service_billing_avg_rate_trend": service_billing_avg_rate_trend,
		"meal_form_stats": meal_form_stats,
		"meal_form_trend": meal_form_trend,
		"meal_form_qty_trend": meal_form_qty_trend,
		"meal_form_by_type": meal_form_by_type,
		"service_detail_trend": service_detail_trend,
		"service_detail_qty_trend": service_detail_qty_trend,
		"service_detail_by_item": service_detail_by_item,
		"provider_by_type": provider_by_type,
		"contractor_by_type": contractor_by_type,
		"meal_provider_amount": meal_provider_amount,
		"department_amount": department_amount,
		"cost_center_amount": cost_center_amount,
		"top_providers": top_providers,
		"top_contractors": top_contractors,
		"top_items_qty": sorted(service_detail_by_item, key=lambda d: d.get("qty") or 0, reverse=True)[:10],
		"top_items_amount": sorted(service_detail_by_item, key=lambda d: d.get("amount") or 0, reverse=True)[:10],
		"top_meal_types_qty": sorted(meal_form_by_type, key=lambda d: d.get("qty") or 0, reverse=True)[:10],
		"top_meal_types_amount": sorted(meal_form_by_type, key=lambda d: d.get("amount") or 0, reverse=True)[:10],
		"billed_split": billed_split,
		"invoiced_split": invoiced_split,
		"pi_amount_trend": pi_amount_trend,
		"pi_avg_trend": pi_avg_trend,
		"sb_by_day": sb_by_day,
		"mf_by_day": mf_by_day,
		"lead_time_buckets": lead_time_buckets,
		"meal_form_scatter": meal_form_scatter,
		"service_billing_list": service_billing_list,
		"meal_form_list": meal_form_list,
		"service_detail_list": service_detail_list,
		"summary_list": summary_list,
		"filters": {
			"service_providers": frappe.get_all(
				"Meal Provider", fields=["name"], filters={"active": 1}, order_by="name asc"
			),
			"contractors": frappe.get_all("Contractor", fields=["name"], order_by="name asc", limit=200),
			"service_types": frappe.get_all("Meal Type", fields=["name"], order_by="name asc"),
		},
	}
