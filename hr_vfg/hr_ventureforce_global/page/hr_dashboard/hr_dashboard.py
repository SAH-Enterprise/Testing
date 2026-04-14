import frappe
from frappe.utils import add_months, get_first_day, get_last_day, getdate, now_datetime, nowdate


# ── Helpers ───────────────────────────────────────────────────────────────────

def _exists(dt):
    try:
        return bool(frappe.db.exists("DocType", dt))
    except Exception:
        return False


def _count(dt, filters=None):
    if not _exists(dt):
        return 0
    try:
        return int(frappe.db.count(dt, filters=filters or {}) or 0)
    except Exception:
        return 0


def _sql(q, p=None):
    try:
        return frappe.db.sql(q, p or [], as_dict=True)
    except Exception:
        return []


def _f(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _get(row, field):
    if not row:
        return 0.0
    try:
        return _f(row.get(field, 0))
    except Exception:
        return 0.0


def _mlabel(d):
    return d.strftime("%b %Y")


# ── EA month key helper ───────────────────────────────────────────────────────
_EA_DATE = "STR_TO_DATE(CONCAT(`year`,'-',`month`,'-01'),'%%Y-%%M-%%d')"


# ── Main API ──────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_dashboard_data(from_date=None, to_date=None):
    today    = getdate(nowdate())

    # Resolve to_date → end of the selected range
    end_date = getdate(to_date) if to_date else today
    cme      = get_last_day(end_date)
    cms      = get_first_day(end_date)           # "current" month for KPIs

    # Build month buckets (from_date → to_date, max 12)
    if from_date:
        start_date  = getdate(from_date)
        months, cur = [], get_first_day(start_date)
        while cur <= cms and len(months) < 12:
            months.append(cur)
            cur = add_months(cur, 1)
        if not months:
            months = [cms]
    else:
        months = [get_first_day(add_months(end_date, i)) for i in range(-5, 1)]

    six_start    = months[0]
    cur_mk       = cms.strftime("%Y-%m")
    month_labels = [_mlabel(ms) for ms in months]

    # ── KPIs (always relative to real today + cms month) ──────────────────────
    active_emp       = _count("Employee",            {"status": "Active"})
    present_today    = _count("Attendance",          {"status": "Present", "attendance_date": today, "docstatus": ["<", 2]})
    absent_today     = _count("Attendance",          {"status": "Absent",  "attendance_date": today, "docstatus": ["<", 2]})
    open_jobs        = _count("Job Opening",         {"status": "Open"})
    new_joiners      = _count("Employee",            {"date_of_joining": ["between", [cms, cme]]})
    pending_leaves   = _count("Leave Application",   {"status": "Open", "from_date": [">=", today]})
    salary_slips_mo  = _count("Salary Slip",         {"docstatus": 1, "posting_date": ["between", [cms, cme]]})
    payroll_entries  = _count("Payroll Entry",       {"posting_date": ["between", [cms, cme]]})
    onboarding_open  = _count("Employee Onboarding", {"status": ["in", ["In Progress", "Pending"]]})
    sep_pending      = _count("Employee Separation", {"status": ["in", ["Pending", "In Progress"]]})
    interviews_sched = _count("Interview",           {"status": ["in", ["Scheduled", "Under Review"]]})
    exp_claims_mo    = _count("Expense Claim",       {"docstatus": 1, "posting_date": ["between", [cms, cme]]})
    add_sal_mo       = _count("Additional Salary",   {"docstatus": 1, "payroll_date": ["between", [cms, cme]]})

    # ── Employee Attendance 6M — confirmed fields only ────────────────────────
    att_rows = _sql("""
        SELECT
            DATE_FORMAT({ea_date}, '%%Y-%%m') AS mk,
            SUM(CAST(COALESCE(NULLIF(present_days,                  ''), '0') AS DECIMAL(18,2))) AS pd,
            SUM(CAST(COALESCE(NULLIF(total_lates,                   ''), '0') AS DECIMAL(18,2))) AS lm,
            SUM(CAST(COALESCE(NULLIF(total_absents,                 ''), '0') AS DECIMAL(18,2))) AS ab,
            SUM(CAST(COALESCE(NULLIF(total_early_goings,            ''), '0') AS DECIMAL(18,2))) AS eg,
            SUM(CAST(COALESCE(NULLIF(over_time,                     ''), '0') AS DECIMAL(18,2))) AS ot,
            SUM(CAST(COALESCE(NULLIF(approved_overtime_le,          ''), '0') AS DECIMAL(18,2))) AS aot,
            SUM(CAST(COALESCE(NULLIF(total_absent_check_in_missing, ''), '0') AS DECIMAL(18,2))) AS ci_miss,
            SUM(CAST(COALESCE(NULLIF(total_absent_missing_check_out,''), '0') AS DECIMAL(18,2))) AS co_miss,
            SUM(CAST(COALESCE(NULLIF(total_working_days,            ''), '0') AS DECIMAL(18,2))) AS wd,
            SUM(CAST(COALESCE(NULLIF(total_half_days,               ''), '0') AS DECIMAL(18,2))) AS hd
        FROM `tabEmployee Attendance`
        WHERE {ea_date} BETWEEN %s AND %s
        GROUP BY mk ORDER BY mk
    """.format(ea_date=_EA_DATE), [six_start, cme])

    att_map = {r.mk: r for r in att_rows}

    def aseries(field):
        return [round(_get(att_map.get(ms.strftime("%Y-%m")), field), 2) for ms in months]

    # Current month summary for the donut
    cur_row      = att_map.get(cur_mk)
    pd_total     = _get(cur_row, "pd")
    wd_total     = _get(cur_row, "wd")
    att_rate     = round(pd_total / wd_total * 100, 1) if wd_total else 0.0
    month_summary = {
        "present": round(pd_total, 1),
        "late":    round(_get(cur_row, "lm"), 1),
        "absent":  round(_get(cur_row, "ab"), 1),
        "early":   round(_get(cur_row, "eg"), 1),
        "halfday": round(_get(cur_row, "hd"), 1),
        "wd":      round(wd_total, 1),
    }

    # ── Branch / Unit wise attendance (replaces shift — no shift field in EA) ─
    branch_rows = _sql("""
        SELECT
            COALESCE(NULLIF(unit,''), 'Unassigned') AS branch,
            SUM(CAST(COALESCE(NULLIF(present_days,  ''), '0') AS DECIMAL(18,2))) AS pd,
            SUM(CAST(COALESCE(NULLIF(total_lates,   ''), '0') AS DECIMAL(18,2))) AS lm,
            SUM(CAST(COALESCE(NULLIF(total_absents, ''), '0') AS DECIMAL(18,2))) AS ab
        FROM `tabEmployee Attendance`
        WHERE {ea_date} BETWEEN %s AND %s
        GROUP BY branch ORDER BY pd DESC LIMIT 10
    """.format(ea_date=_EA_DATE), [six_start, cme])
    branch_labels = [r.branch for r in branch_rows]
    branch_pd     = [round(_f(r.pd), 1) for r in branch_rows]
    branch_lm     = [round(_f(r.lm), 1) for r in branch_rows]
    branch_ab     = [round(_f(r.ab), 1) for r in branch_rows]

    # ── Designation-wise attendance (current month) ────────────────────────────
    desig_rows = _sql("""
        SELECT
            COALESCE(NULLIF(designation,''), 'Unspecified') AS desig,
            SUM(CAST(COALESCE(NULLIF(present_days,  ''), '0') AS DECIMAL(18,2))) AS pd,
            SUM(CAST(COALESCE(NULLIF(total_lates,   ''), '0') AS DECIMAL(18,2))) AS lm,
            SUM(CAST(COALESCE(NULLIF(total_absents, ''), '0') AS DECIMAL(18,2))) AS ab
        FROM `tabEmployee Attendance`
        WHERE {ea_date} = %s
        GROUP BY desig ORDER BY pd DESC LIMIT 10
    """.format(ea_date=_EA_DATE), [cms])
    desig_labels = [r.desig for r in desig_rows]
    desig_pd     = [round(_f(r.pd), 1) for r in desig_rows]
    desig_lm     = [round(_f(r.lm), 1) for r in desig_rows]
    desig_ab     = [round(_f(r.ab), 1) for r in desig_rows]

    # ── Late Over Time 6M ─────────────────────────────────────────────────────
    lot_rows = _sql("""
        SELECT
            DATE_FORMAT(date,'%%Y-%%m') AS mk,
            COUNT(*) AS reqs,
            SUM(CAST(COALESCE(NULLIF(total_over_time,    ''), '0') AS DECIMAL(18,4))) AS tot_ot,
            SUM(CAST(COALESCE(NULLIF(approved_over_time, ''), '0') AS DECIMAL(18,4))) AS appr_ot
        FROM `tabLate Over Time`
        WHERE ifnull(docstatus,0) < 2 AND date BETWEEN %s AND %s
        GROUP BY mk ORDER BY mk
    """, [six_start, cme])
    lot_map  = {r.mk: r for r in lot_rows}
    lot_reqs = [int(_get(lot_map.get(ms.strftime("%Y-%m")), "reqs"))    for ms in months]
    lot_ot   = [round(_get(lot_map.get(ms.strftime("%Y-%m")), "tot_ot"),  2) for ms in months]
    lot_aot  = [round(_get(lot_map.get(ms.strftime("%Y-%m")), "appr_ot"), 2) for ms in months]

    # ── Recruitment ────────────────────────────────────────────────────────────
    applicants_mo = _count("Job Applicant", {"creation": ["between", [cms, cme]]})
    offers_mo     = _count("Job Offer",     {"creation": ["between", [cms, cme]]})

    app_rows = _sql("""
        SELECT DATE_FORMAT(creation,'%%Y-%%m') AS mk, COUNT(*) AS cnt
        FROM `tabJob Applicant` WHERE creation >= %s
        GROUP BY mk ORDER BY mk
    """, [six_start])
    app_map          = {r.mk: int(r.cnt or 0) for r in app_rows}
    applicants_trend = [app_map.get(ms.strftime("%Y-%m"), 0) for ms in months]

    job_dept_rows = _sql("""
        SELECT COALESCE(NULLIF(department,''), 'Unassigned') AS dept, COUNT(*) AS cnt
        FROM `tabJob Opening` WHERE status = 'Open'
        GROUP BY dept ORDER BY cnt DESC LIMIT 8
    """)

    # ── Payroll 6M ─────────────────────────────────────────────────────────────
    ss_rows = _sql("""
        SELECT DATE_FORMAT(COALESCE(posting_date,start_date,creation),'%%Y-%%m') AS mk, COUNT(*) AS cnt
        FROM `tabSalary Slip`
        WHERE docstatus=1 AND COALESCE(posting_date,start_date,creation) BETWEEN %s AND %s
        GROUP BY mk ORDER BY mk
    """, [six_start, cme])
    ss_map       = {r.mk: int(r.cnt or 0) for r in ss_rows}
    salary_trend = [ss_map.get(ms.strftime("%Y-%m"), 0) for ms in months]

    adv_rows = _sql("""
        SELECT DATE_FORMAT(COALESCE(posting_date,creation),'%%Y-%%m') AS mk, COUNT(*) AS cnt
        FROM `tabEmployee Advance`
        WHERE docstatus=1 AND COALESCE(posting_date,creation) BETWEEN %s AND %s
        GROUP BY mk ORDER BY mk
    """, [six_start, cme])
    adv_map       = {r.mk: int(r.cnt or 0) for r in adv_rows}
    advance_trend = [adv_map.get(ms.strftime("%Y-%m"), 0) for ms in months]

    # Expense Claim — try posting_date then creation
    exp_rows = _sql("""
        SELECT DATE_FORMAT(COALESCE(posting_date,creation),'%%Y-%%m') AS mk, COUNT(*) AS cnt
        FROM `tabExpense Claim`
        WHERE docstatus=1 AND COALESCE(posting_date,creation) BETWEEN %s AND %s
        GROUP BY mk ORDER BY mk
    """, [six_start, cme])
    exp_map       = {r.mk: int(r.cnt or 0) for r in exp_rows}
    expense_trend = [exp_map.get(ms.strftime("%Y-%m"), 0) for ms in months]

    # Additional Salary — try payroll_date then creation
    add_sal_rows = _sql("""
        SELECT DATE_FORMAT(COALESCE(payroll_date,creation),'%%Y-%%m') AS mk, COUNT(*) AS cnt
        FROM `tabAdditional Salary`
        WHERE docstatus=1 AND COALESCE(payroll_date,creation) BETWEEN %s AND %s
        GROUP BY mk ORDER BY mk
    """, [six_start, cme])
    add_sal_map             = {r.mk: int(r.cnt or 0) for r in add_sal_rows}
    additional_salary_trend = [add_sal_map.get(ms.strftime("%Y-%m"), 0) for ms in months]

    # ── Employee Lifecycle 6M ─────────────────────────────────────────────────
    joiner_rows = _sql("""
        SELECT DATE_FORMAT(COALESCE(date_of_joining,creation),'%%Y-%%m') AS mk, COUNT(*) AS cnt
        FROM `tabEmployee`
        WHERE COALESCE(date_of_joining,creation) BETWEEN %s AND %s
        GROUP BY mk ORDER BY mk
    """, [six_start, cme])
    joiner_map    = {r.mk: int(r.cnt or 0) for r in joiner_rows}
    joiners_trend = [joiner_map.get(ms.strftime("%Y-%m"), 0) for ms in months]

    relieved_rows = _sql("""
        SELECT DATE_FORMAT(relieving_date,'%%Y-%%m') AS mk, COUNT(*) AS cnt
        FROM `tabEmployee`
        WHERE relieving_date IS NOT NULL AND relieving_date BETWEEN %s AND %s
        GROUP BY mk ORDER BY mk
    """, [six_start, cme])
    relieved_map   = {r.mk: int(r.cnt or 0) for r in relieved_rows}
    relieved_trend = [relieved_map.get(ms.strftime("%Y-%m"), 0) for ms in months]

    # ── Department Performance ────────────────────────────────────────────────
    dept_rows = _sql("""
        SELECT
            COALESCE(NULLIF(department,''), 'Unassigned') AS dept,
            SUM(CAST(COALESCE(NULLIF(present_days,       ''), '0') AS DECIMAL(18,2))) AS pd,
            SUM(CAST(COALESCE(NULLIF(total_working_days, ''), '0') AS DECIMAL(18,2))) AS wd,
            SUM(CAST(COALESCE(NULLIF(total_lates,        ''), '0') AS DECIMAL(18,2))) AS lm,
            SUM(CAST(COALESCE(NULLIF(total_absents,      ''), '0') AS DECIMAL(18,2))) AS ab,
            SUM(CAST(COALESCE(NULLIF(over_time,          ''), '0') AS DECIMAL(18,2))) AS ot
        FROM `tabEmployee Attendance`
        WHERE {ea_date} BETWEEN %s AND %s
        GROUP BY dept ORDER BY pd DESC LIMIT 12
    """.format(ea_date=_EA_DATE), [six_start, cme])

    dept_labels, dept_rate, dept_lm, dept_ab, dept_ot = [], [], [], [], []
    for r in dept_rows:
        wd   = _f(r.wd)
        pd   = _f(r.pd)
        rate = round(pd / wd * 100, 1) if wd else 0.0
        dept_labels.append(r.dept)
        dept_rate.append(rate)
        dept_lm.append(round(_f(r.lm), 1))
        dept_ab.append(round(_f(r.ab), 1))
        dept_ot.append(round(_f(r.ot), 1))

    # ── Employee distribution ──────────────────────────────────────────────────
    emp_dept_rows = _sql("""
        SELECT COALESCE(NULLIF(department,''), 'Unassigned') AS dept, COUNT(*) AS cnt
        FROM `tabEmployee` WHERE status='Active'
        GROUP BY dept ORDER BY cnt DESC LIMIT 12
    """)
    emp_type_rows = _sql("""
        SELECT COALESCE(NULLIF(employment_type,''), 'Unspecified') AS etype, COUNT(*) AS cnt
        FROM `tabEmployee` WHERE status='Active'
        GROUP BY etype ORDER BY cnt DESC LIMIT 8
    """)
    gender_rows = _sql("""
        SELECT COALESCE(NULLIF(gender,''), 'Not Set') AS g, COUNT(*) AS cnt
        FROM `tabEmployee` WHERE status='Active'
        GROUP BY g ORDER BY cnt DESC
    """)

    # ── Leave ──────────────────────────────────────────────────────────────────
    leave_type_rows = _sql("""
        SELECT leave_type, COUNT(*) AS cnt
        FROM `tabLeave Application`
        WHERE from_date BETWEEN %s AND %s AND docstatus < 2
        GROUP BY leave_type ORDER BY cnt DESC LIMIT 8
    """, [six_start, cme])

    leave_stat_rows = _sql("""
        SELECT status, COUNT(*) AS cnt
        FROM `tabLeave Application`
        WHERE from_date BETWEEN %s AND %s AND docstatus < 2
        GROUP BY status
    """, [six_start, cme])
    leave_stat_map = {r.status: int(r.cnt or 0) for r in leave_stat_rows}

    leave_6m_rows = _sql("""
        SELECT DATE_FORMAT(from_date,'%%Y-%%m') AS mk, COUNT(*) AS cnt
        FROM `tabLeave Application`
        WHERE from_date BETWEEN %s AND %s AND docstatus < 2
        GROUP BY mk ORDER BY mk
    """, [six_start, cme])
    leave_6m_map   = {r.mk: int(r.cnt or 0) for r in leave_6m_rows}
    leave_6m_trend = [leave_6m_map.get(ms.strftime("%Y-%m"), 0) for ms in months]

    # ─────────────────────────────────────────────────────────────────────────
    return {
        "generated_on": now_datetime().isoformat(),
        "period_label": "{} – {}".format(_mlabel(months[0]), _mlabel(months[-1])),
        "months":       month_labels,

        "kpis": {
            "active_employees":   active_emp,
            "present_today":      present_today,
            "absent_today":       absent_today,
            "attendance_rate":    att_rate,
            "open_jobs":          open_jobs,
            "new_joiners_month":  new_joiners,
            "pending_leaves":     pending_leaves,
            "salary_slips_month": salary_slips_mo,
            "payroll_entries":    payroll_entries,
            "onboarding_open":    onboarding_open,
            "separation_pending": sep_pending,
            "interviews_sched":   interviews_sched,
            "expense_claims":     exp_claims_mo,
            "add_salary":         add_sal_mo,
        },

        "attendance": {
            "present":          aseries("pd"),
            "late":             aseries("lm"),
            "absent":           aseries("ab"),
            "early":            aseries("eg"),
            "overtime":         aseries("ot"),
            "approved_ot":      aseries("aot"),
            "missed_check_in":  aseries("ci_miss"),
            "missed_check_out": aseries("co_miss"),
            "month_summary":    month_summary,
            "today": {
                "Present":  present_today,
                "Absent":   absent_today,
            },
        },

        "branch": {
            "labels": branch_labels,
            "pd":     branch_pd,
            "lm":     branch_lm,
            "ab":     branch_ab,
        },

        "designation": {
            "labels": desig_labels,
            "pd":     desig_pd,
            "lm":     desig_lm,
            "ab":     desig_ab,
        },

        "lot": {
            "requests":    lot_reqs,
            "total_ot":    lot_ot,
            "approved_ot": lot_aot,
        },

        "recruitment": {
            "open_jobs":        open_jobs,
            "applicants_month": applicants_mo,
            "interviews":       interviews_sched,
            "offers_month":     offers_mo,
            "applicants_trend": applicants_trend,
            "dept_labels":      [r.dept for r in job_dept_rows],
            "dept_counts":      [int(r.cnt or 0) for r in job_dept_rows],
        },

        "payroll": {
            "salary_trend":            salary_trend,
            "advance_trend":           advance_trend,
            "expense_trend":           expense_trend,
            "additional_salary_trend": additional_salary_trend,
        },

        "lifecycle": {
            "joiners":  joiners_trend,
            "relieved": relieved_trend,
            "leave_trend": leave_6m_trend,
        },

        "department": {
            "labels":       dept_labels,
            "present_rate": dept_rate,
            "late":         dept_lm,
            "absent":       dept_ab,
            "overtime":     dept_ot,
        },

        "employee": {
            "dept_labels":   [r.dept  for r in emp_dept_rows],
            "dept_counts":   [int(r.cnt or 0) for r in emp_dept_rows],
            "type_labels":   [r.etype for r in emp_type_rows],
            "type_counts":   [int(r.cnt or 0) for r in emp_type_rows],
            "gender_labels": [r.g     for r in gender_rows],
            "gender_counts": [int(r.cnt or 0) for r in gender_rows],
        },

        "leave": {
            "type_labels": [r.leave_type for r in leave_type_rows],
            "type_counts": [int(r.cnt or 0) for r in leave_type_rows],
            "approved":    leave_stat_map.get("Approved", 0),
            "open":        leave_stat_map.get("Open", 0),
            "rejected":    leave_stat_map.get("Rejected", 0),
            "trend":       leave_6m_trend,
        },
    }
