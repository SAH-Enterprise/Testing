/* ─── State ──────────────────────────────────────────────────────────────── */
if (!window._hrd) window._hrd = { charts: {}, loading: false };

/* ─── Page lifecycle ─────────────────────────────────────────────────────── */
frappe.pages['hr-dashboard'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: 'HR Dashboard', single_column: true });
	_hrd_build(wrapper);
};

frappe.pages['hr-dashboard'].on_page_show = function (wrapper) {
	if (!window._hrd.loading) _hrd_refresh(wrapper);
};

/* ─── Build shell ────────────────────────────────────────────────────────── */
function _hrd_build(wrapper) {
	var $m = $(wrapper).find('.layout-main-section');
	$m.empty().append(_hrd_css() + _hrd_html());

	// Set default dates: 6 months ago → today
	var today   = frappe.datetime.get_today();
	var sixAgo  = frappe.datetime.add_months(today, -5);
	var fromMs  = frappe.datetime.month_start(sixAgo);
	$m.find('#hrd-from').val(fromMs);
	$m.find('#hrd-to').val(today);

	$m.find('#hrd-btn-apply').on('click',   function () { _hrd_refresh(wrapper); });
	$m.find('#hrd-btn-reset').on('click',   function () {
		$m.find('#hrd-from').val(fromMs);
		$m.find('#hrd-to').val(today);
		_hrd_refresh(wrapper);
	});
	$m.find('#hrd-btn-refresh').on('click', function () { _hrd_refresh(wrapper); });
}

/* ─── Data pipeline ──────────────────────────────────────────────────────── */
function _hrd_refresh(wrapper) {
	window._hrd.loading = true;
	_hrd_loading(wrapper, true);
	_hrd_apex_ready()
		.then(function ()   { _hrd_fetch(wrapper); })
		.catch(function (e) {
			console.error('[HRD] ApexCharts load error', e);
			window._hrd.loading = false;
			_hrd_error(wrapper, 'ApexCharts could not be loaded.');
		});
}

function _hrd_apex_ready() {
	if (window.ApexCharts) return Promise.resolve();
	return new Promise(function (resolve, reject) {
		var s = document.createElement('script');
		s.src = '/assets/management_dashboard/js/apexcharts.min.js';
		s.onload = resolve; s.onerror = reject;
		document.head.appendChild(s);
	});
}

function _hrd_fetch(wrapper) {
	var $m       = $(wrapper).find('.layout-main-section');
	var from_date = $m.find('#hrd-from').val() || '';
	var to_date   = $m.find('#hrd-to').val()   || '';

	frappe.call({
		method: 'hr_vfg.hr_ventureforce_global.page.hr_dashboard.hr_dashboard.get_dashboard_data',
		args:   { from_date: from_date, to_date: to_date },
		callback: function (r) {
			window._hrd.loading = false;
			if (!r.message) { _hrd_error(wrapper, 'Server returned no data.'); return; }
			_hrd_render(wrapper, r.message);
		},
		error: function () {
			window._hrd.loading = false;
			_hrd_error(wrapper, 'Failed to load dashboard data. Please try again.');
		},
	});
}

/* ─── Render ─────────────────────────────────────────────────────────────── */
function _hrd_render(wrapper, d) {
	_hrd_destroy();
	var $m = $(wrapper).find('.layout-main-section');
	$m.find('#hrd-period').text(d.period_label || '');
	$m.find('#hrd-updated').text('Updated ' + frappe.datetime.now_time());
	_hrd_kpis($m, d.kpis || {});
	_hrd_loading(wrapper, false);
	$m.find('#hrd-content').show();
	setTimeout(function () { _hrd_charts($m, d); }, 20);
}

/* ─── KPI strip ──────────────────────────────────────────────────────────── */
function _hrd_kpis($m, k) {
	var n   = function (v) { return frappe.format(v || 0, { fieldtype: 'Int' }); };
	var pct = function (v) { return (v || 0).toFixed(1) + '%'; };
	var cards = [
		{ lbl: 'Active Employees',  val: n(k.active_employees),   ico: '👥', c: '#4361ee', bg: '#eef2ff' },
		{ lbl: 'Present Today',     val: n(k.present_today),       ico: '✅', c: '#10b981', bg: '#ecfdf5' },
		{ lbl: 'Absent Today',      val: n(k.absent_today),        ico: '🚫', c: '#ef4444', bg: '#fef2f2' },
		{ lbl: 'Attendance Rate',   val: pct(k.attendance_rate),   ico: '📈', c: '#0d9488', bg: '#f0fdfa', sub: 'Selected Period' },
		{ lbl: 'Open Jobs',         val: n(k.open_jobs),           ico: '💼', c: '#8b5cf6', bg: '#f5f3ff' },
		{ lbl: 'Interviews',        val: n(k.interviews_sched),    ico: '🗣️',  c: '#6366f1', bg: '#eef2ff', sub: 'Scheduled' },
		{ lbl: 'New Joiners',       val: n(k.new_joiners_month),   ico: '🚀', c: '#f59e0b', bg: '#fffbeb', sub: 'Period End Month' },
		{ lbl: 'Pending Leaves',    val: n(k.pending_leaves),      ico: '📋', c: '#06b6d4', bg: '#ecfeff' },
		{ lbl: 'Salary Slips',      val: n(k.salary_slips_month),  ico: '💰', c: '#4361ee', bg: '#eef2ff', sub: 'Period End Month' },
		{ lbl: 'Payroll Entries',   val: n(k.payroll_entries),     ico: '📊', c: '#7c3aed', bg: '#f5f3ff', sub: 'Period End Month' },
		{ lbl: 'Expense Claims',    val: n(k.expense_claims),      ico: '🧾', c: '#db2777', bg: '#fdf2f8', sub: 'Period End Month' },
		{ lbl: 'Additional Salary', val: n(k.add_salary),          ico: '➕', c: '#059669', bg: '#ecfdf5', sub: 'Period End Month' },
		{ lbl: 'Onboarding',        val: n(k.onboarding_open),     ico: '🏢', c: '#0284c7', bg: '#f0f9ff', sub: 'In Progress' },
		{ lbl: 'Separations',       val: n(k.separation_pending),  ico: '🔄', c: '#f43f5e', bg: '#fff1f2', sub: 'Pending' },
	];
	$m.find('#hrd-kpi-strip').html(
		cards.map(function (c) {
			return '<div class="hrd-kpi" style="--kc:' + c.c + ';--kb:' + c.bg + '">' +
				'<div class="hrd-kpi-ico">' + c.ico + '</div>' +
				'<div><div class="hrd-kpi-val" style="color:' + c.c + '">' + c.val + '</div>' +
				'<div class="hrd-kpi-lbl">' + c.lbl + '</div>' +
				(c.sub ? '<div class="hrd-kpi-sub">' + c.sub + '</div>' : '') + '</div></div>';
		}).join('')
	);
}

/* ─── Charts ─────────────────────────────────────────────────────────────── */
function _hrd_charts($m, d) {
	var months = d.months     || [];
	var att    = d.attendance || {};
	var br     = d.branch     || {};
	var desig  = d.designation|| {};
	var lot    = d.lot        || {};
	var rec    = d.recruitment|| {};
	var pay    = d.payroll    || {};
	var life   = d.lifecycle  || {};
	var dept   = d.department || {};
	var emp    = d.employee   || {};
	var lv     = d.leave      || {};
	var ms     = att.month_summary || {};

	var B    = { fontFamily: '"Space Grotesk","Inter",sans-serif', toolbar: { show: false } };
	var GRID = { borderColor: 'rgba(0,0,0,0.06)', strokeDashArray: 3 };

	/* ── 1. Attendance Trend — stacked bar ─────────────────────────────────── */
	_c('hrd-c-att', {
		chart: _x(B, { type: 'bar', height: 320, stacked: true }),
		colors: ['#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
		plotOptions: { bar: { columnWidth: '58%', borderRadius: 3 } },
		dataLabels: { enabled: false },
		stroke: { show: false },
		xaxis: { categories: months },
		yaxis: { title: { text: 'Days' } },
		legend: { position: 'top', horizontalAlign: 'left' },
		grid: GRID,
		tooltip: { shared: true, intersect: false },
		series: [
			{ name: 'Present',     data: att.present || [] },
			{ name: 'Late',        data: att.late    || [] },
			{ name: 'Absent',      data: att.absent  || [] },
			{ name: 'Early Going', data: att.early   || [] },
		],
	});

	/* ── 2. This Month at a Glance — donut from Employee Attendance ─────────── */
	var sumVals  = [ms.present || 0, ms.late || 0, ms.absent || 0, ms.early || 0, ms.halfday || 0];
	var sumTotal = sumVals.reduce(function (a, b) { return a + b; }, 0);
	_c('hrd-c-month-donut', {
		chart: _x(B, { type: 'donut', height: 320 }),
		labels: ['Present', 'Late', 'Absent', 'Early Going', 'Half Day'],
		colors: ['#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'],
		series: sumVals,
		legend: { position: 'bottom' },
		plotOptions: {
			pie: {
				donut: {
					size: '65%',
					labels: {
						show: true,
						total: {
							show: true, label: 'Working Days',
							fontSize: '13px', fontWeight: 700,
							formatter: function () { return (ms.wd || 0) + ' days'; },
						},
					},
				},
			},
		},
		dataLabels: { enabled: sumTotal > 0, dropShadow: { enabled: false } },
		tooltip: { y: { formatter: function (v) { return v + ' days'; } } },
	});

	/* ── 3. Overtime vs Approved OT — area ─────────────────────────────────── */
	_c('hrd-c-ot', {
		chart: _x(B, { type: 'area', height: 240 }),
		colors: ['#4361ee', '#10b981'],
		fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.28, opacityTo: 0.02 } },
		stroke: { curve: 'smooth', width: 2.5 },
		xaxis: { categories: months },
		yaxis: { title: { text: 'Hours' } },
		dataLabels: { enabled: false },
		legend: { position: 'top', horizontalAlign: 'left' },
		grid: GRID,
		markers: { size: 4, strokeWidth: 0, hover: { size: 7 } },
		tooltip: { shared: true, intersect: false, y: { formatter: function (v) { return (+v || 0).toFixed(2) + ' hrs'; } } },
		series: [
			{ name: 'Actual OT',   data: att.overtime    || [] },
			{ name: 'Approved OT', data: att.approved_ot || [] },
		],
	});

	/* ── 4. Late Over Time Requests — area ──────────────────────────────────── */
	_c('hrd-c-lot', {
		chart: _x(B, { type: 'area', height: 240 }),
		colors: ['#6366f1', '#f59e0b'],
		fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.28, opacityTo: 0.02 } },
		stroke: { curve: 'smooth', width: 2.5 },
		xaxis: { categories: months },
		yaxis: { title: { text: 'Hours' } },
		dataLabels: { enabled: false },
		legend: { position: 'top', horizontalAlign: 'left' },
		grid: GRID,
		markers: { size: 4, strokeWidth: 0, hover: { size: 7 } },
		tooltip: { shared: true, intersect: false, y: { formatter: function (v) { return (+v || 0).toFixed(2) + ' hrs'; } } },
		series: [
			{ name: 'Total OT hrs',    data: lot.total_ot    || [] },
			{ name: 'Approved OT hrs', data: lot.approved_ot || [] },
		],
	});

	/* ── 5. Missing Logs — grouped bar ─────────────────────────────────────── */
	_c('hrd-c-missing', {
		chart: _x(B, { type: 'bar', height: 260 }),
		colors: ['#ef4444', '#f97316'],
		plotOptions: { bar: { columnWidth: '58%', borderRadius: 3 } },
		dataLabels: { enabled: false },
		xaxis: { categories: months },
		yaxis: { title: { text: 'Count' } },
		legend: { position: 'top', horizontalAlign: 'left' },
		grid: GRID,
		tooltip: { shared: true, intersect: false },
		series: [
			{ name: 'Missed Check-In',  data: att.missed_check_in  || [] },
			{ name: 'Missed Check-Out', data: att.missed_check_out || [] },
		],
	});

	/* ── 6. Branch-wise Attendance — horizontal bar (replaces broken shift) ─── */
	var bH = Math.max(260, (br.labels || []).length * 36 + 60);
	_c('hrd-c-branch', {
		chart: _x(B, { type: 'bar', height: bH }),
		colors: ['#10b981', '#f59e0b', '#ef4444'],
		plotOptions: { bar: { horizontal: true, borderRadius: 4, barHeight: '58%' } },
		dataLabels: { enabled: false },
		xaxis: { categories: br.labels || [] },
		legend: { position: 'top', horizontalAlign: 'left' },
		grid: GRID,
		tooltip: { shared: true, intersect: false },
		series: [
			{ name: 'Present',  data: br.pd || [] },
			{ name: 'Late',     data: br.lm || [] },
			{ name: 'Absent',   data: br.ab || [] },
		],
	});

	/* ── 7. Designation-wise Attendance — horizontal bar ────────────────────── */
	var dgH = Math.max(260, (desig.labels || []).length * 36 + 60);
	_c('hrd-c-desig', {
		chart: _x(B, { type: 'bar', height: dgH }),
		colors: ['#10b981', '#f59e0b', '#ef4444'],
		plotOptions: { bar: { horizontal: true, borderRadius: 4, barHeight: '58%' } },
		dataLabels: { enabled: false },
		xaxis: { categories: desig.labels || [] },
		legend: { position: 'top', horizontalAlign: 'left' },
		grid: GRID,
		tooltip: { shared: true, intersect: false },
		series: [
			{ name: 'Present',  data: desig.pd || [] },
			{ name: 'Late',     data: desig.lm || [] },
			{ name: 'Absent',   data: desig.ab || [] },
		],
	});

	/* ── 8. Recruitment Pipeline — distributed horizontal bar ───────────────── */
	_c('hrd-c-funnel', {
		chart: _x(B, { type: 'bar', height: 280 }),
		colors: ['#4361ee', '#8b5cf6', '#f59e0b', '#10b981'],
		plotOptions: { bar: { horizontal: true, distributed: true, borderRadius: 6, barHeight: '52%', dataLabels: { position: 'top' } } },
		dataLabels: { enabled: true, offsetX: 8, style: { fontSize: '13px', fontWeight: 700, colors: ['#374151'] } },
		xaxis: { categories: ['Job Openings', 'Applicants', 'Interviews', 'Offers'] },
		legend: { show: false },
		grid: GRID,
		series: [{ name: 'Count', data: [rec.open_jobs || 0, rec.applicants_month || 0, rec.interviews || 0, rec.offers_month || 0] }],
	});

	/* ── 9. Applicants Trend — area ─────────────────────────────────────────── */
	_c('hrd-c-applicants', {
		chart: _x(B, { type: 'area', height: 280 }),
		colors: ['#8b5cf6'],
		fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.35, opacityTo: 0.02 } },
		stroke: { curve: 'smooth', width: 2.5 },
		xaxis: { categories: months },
		dataLabels: { enabled: false },
		grid: GRID,
		markers: { size: 4, strokeWidth: 0, hover: { size: 7 } },
		series: [{ name: 'Applicants', data: rec.applicants_trend || [] }],
	});

	/* ── 10. Open Jobs by Dept — horizontal bar ─────────────────────────────── */
	var jdH = Math.max(200, (rec.dept_labels || []).length * 34 + 60);
	_c('hrd-c-job-dept', {
		chart: _x(B, { type: 'bar', height: jdH }),
		colors: ['#4361ee'],
		plotOptions: { bar: { horizontal: true, borderRadius: 5, barHeight: '55%', dataLabels: { position: 'top' } } },
		dataLabels: { enabled: true, offsetX: 6, style: { fontSize: '12px', fontWeight: 700, colors: ['#374151'] } },
		xaxis: { categories: rec.dept_labels || [] },
		legend: { show: false },
		grid: GRID,
		series: [{ name: 'Open Jobs', data: rec.dept_counts || [] }],
	});

	/* ── 11. Salary Slips & Advances — grouped bar ──────────────────────────── */
	_c('hrd-c-payroll', {
		chart: _x(B, { type: 'bar', height: 280 }),
		colors: ['#4361ee', '#06b6d4'],
		plotOptions: { bar: { columnWidth: '55%', borderRadius: 3 } },
		dataLabels: { enabled: false },
		xaxis: { categories: months },
		legend: { position: 'top', horizontalAlign: 'left' },
		grid: GRID,
		tooltip: { shared: true, intersect: false },
		series: [
			{ name: 'Salary Slips', data: pay.salary_trend  || [] },
			{ name: 'Advances',     data: pay.advance_trend || [] },
		],
	});

	/* ── 12. Expense Claims & Additional Salary — area ──────────────────────── */
	_c('hrd-c-expense', {
		chart: _x(B, { type: 'area', height: 280 }),
		colors: ['#db2777', '#059669'],
		fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.3, opacityTo: 0.02 } },
		stroke: { curve: 'smooth', width: 2.5 },
		xaxis: { categories: months },
		dataLabels: { enabled: false },
		legend: { position: 'top', horizontalAlign: 'left' },
		grid: GRID,
		markers: { size: 4, strokeWidth: 0, hover: { size: 7 } },
		tooltip: { shared: true, intersect: false },
		series: [
			{ name: 'Expense Claims',    data: pay.expense_trend           || [] },
			{ name: 'Additional Salary', data: pay.additional_salary_trend || [] },
		],
	});

	/* ── 13. Leave Type — donut ─────────────────────────────────────────────── */
	var lvTotal = (lv.type_counts || []).reduce(function (a, b) { return a + b; }, 0);
	_c('hrd-c-leave-type', {
		chart: _x(B, { type: 'donut', height: 280 }),
		labels:  lv.type_labels && lv.type_labels.length ? lv.type_labels : ['No Data'],
		series:  lv.type_counts && lv.type_counts.length ? lv.type_counts : [1],
		colors:  ['#4361ee', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#f43f5e', '#0d9488'],
		legend: { position: 'bottom', fontSize: '11px' },
		plotOptions: { pie: { donut: { size: '62%', labels: { show: true, total: { show: true, label: 'Total', fontSize: '12px', formatter: function () { return lvTotal; } } } } } },
		dataLabels: { enabled: lvTotal > 0, dropShadow: { enabled: false } },
	});

	/* ── 14. Leave Status — column ──────────────────────────────────────────── */
	_c('hrd-c-leave-status', {
		chart: _x(B, { type: 'bar', height: 280 }),
		colors: ['#10b981', '#f59e0b', '#ef4444'],
		plotOptions: { bar: { columnWidth: '45%', borderRadius: 6, distributed: true } },
		dataLabels: { enabled: true, style: { fontSize: '14px', fontWeight: 700, colors: ['#374151'] } },
		xaxis: { categories: ['Approved', 'Pending / Open', 'Rejected'] },
		legend: { show: false },
		grid: GRID,
		series: [{ name: 'Applications', data: [lv.approved || 0, lv.open || 0, lv.rejected || 0] }],
	});

	/* ── 15. Leave 6M Trend — area ──────────────────────────────────────────── */
	_c('hrd-c-leave-trend', {
		chart: _x(B, { type: 'area', height: 230 }),
		colors: ['#06b6d4'],
		fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.32, opacityTo: 0.02 } },
		stroke: { curve: 'smooth', width: 2.5 },
		xaxis: { categories: months },
		dataLabels: { enabled: false },
		grid: GRID,
		markers: { size: 4, strokeWidth: 0, hover: { size: 7 } },
		series: [{ name: 'Leave Applications', data: lv.trend || [] }],
	});

	/* ── 16. Joiners vs Relieved — grouped bar ──────────────────────────────── */
	_c('hrd-c-lifecycle', {
		chart: _x(B, { type: 'bar', height: 280 }),
		colors: ['#10b981', '#ef4444'],
		plotOptions: { bar: { columnWidth: '55%', borderRadius: 3 } },
		dataLabels: { enabled: false },
		xaxis: { categories: months },
		legend: { position: 'top', horizontalAlign: 'left' },
		grid: GRID,
		tooltip: { shared: true, intersect: false },
		series: [
			{ name: 'New Joiners', data: life.joiners  || [] },
			{ name: 'Relieved',    data: life.relieved || [] },
		],
	});

	/* ── 17. Employee headcount by dept — horizontal bar ────────────────────── */
	var edH = Math.max(260, (emp.dept_labels || []).length * 34 + 60);
	_c('hrd-c-emp-dept', {
		chart: _x(B, { type: 'bar', height: edH }),
		colors: ['#4361ee'],
		plotOptions: { bar: { horizontal: true, borderRadius: 5, barHeight: '55%', dataLabels: { position: 'top' } } },
		dataLabels: { enabled: true, offsetX: 6, style: { fontSize: '12px', fontWeight: 700, colors: ['#374151'] } },
		xaxis: { categories: emp.dept_labels || [] },
		legend: { show: false },
		grid: GRID,
		series: [{ name: 'Employees', data: emp.dept_counts || [] }],
	});

	/* ── 18. Employment Type — donut ────────────────────────────────────────── */
	var etTotal = (emp.type_counts || []).reduce(function (a, b) { return a + b; }, 0);
	_c('hrd-c-emp-type', {
		chart: _x(B, { type: 'donut', height: 280 }),
		labels: emp.type_labels && emp.type_labels.length ? emp.type_labels : ['No Data'],
		series: emp.type_counts && emp.type_counts.length ? emp.type_counts : [1],
		colors: ['#4361ee', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#f43f5e', '#0d9488'],
		legend: { position: 'bottom', fontSize: '11px' },
		plotOptions: { pie: { donut: { size: '62%', labels: { show: true, total: { show: true, label: 'Active', fontSize: '13px', fontWeight: 700, formatter: function () { return etTotal; } } } } } },
		dataLabels: { enabled: etTotal > 0, dropShadow: { enabled: false } },
	});

	/* ── 19. Gender — pie ───────────────────────────────────────────────────── */
	var gTotal = (emp.gender_counts || []).reduce(function (a, b) { return a + b; }, 0);
	_c('hrd-c-gender', {
		chart: _x(B, { type: 'pie', height: 280 }),
		labels: emp.gender_labels && emp.gender_labels.length ? emp.gender_labels : ['No Data'],
		series: emp.gender_counts && emp.gender_counts.length ? emp.gender_counts : [1],
		colors: ['#4361ee', '#f43f5e', '#10b981', '#f59e0b'],
		legend: { position: 'bottom', fontSize: '12px' },
		dataLabels: { enabled: gTotal > 0, dropShadow: { enabled: false } },
	});

	/* ── 20. Department Performance — horizontal bar ────────────────────────── */
	var dpH = Math.max(300, (dept.labels || []).length * 40 + 70);
	_c('hrd-c-dept-perf', {
		chart: _x(B, { type: 'bar', height: dpH }),
		colors: ['#4361ee', '#f59e0b', '#ef4444'],
		plotOptions: { bar: { horizontal: true, borderRadius: 4, barHeight: '62%' } },
		dataLabels: { enabled: false },
		xaxis: { categories: dept.labels || [] },
		legend: { position: 'top', horizontalAlign: 'left' },
		grid: GRID,
		tooltip: { shared: true, intersect: false },
		series: [
			{ name: 'Present %', data: dept.present_rate || [] },
			{ name: 'Late',      data: dept.late         || [] },
			{ name: 'Absent',    data: dept.absent       || [] },
		],
	});
}

/* ─── Chart factory with no-data guard ───────────────────────────────────── */
function _c(id, opts) {
	var el = document.getElementById(id);
	if (!el) return;

	/* Check if all numeric values are zero */
	var hasData = false;
	(opts.series || []).forEach(function (s) {
		var arr = Array.isArray(s.data) ? s.data : (typeof s === 'number' ? [s] : []);
		if (arr.some(function (v) { return (+v || 0) > 0; })) hasData = true;
	});
	/* Donuts/pies use top-level series */
	if (!opts.series || !Array.isArray(opts.series[0])) {
		if ((opts.chart.type === 'donut' || opts.chart.type === 'pie') && opts.series) {
			if ((opts.series).some(function (v) { return (+v || 0) > 0; })) hasData = true;
		}
	}

	if (!hasData) {
		el.innerHTML = '<div class="hrd-nodata"><div class="hrd-nodata-ico">📭</div><p>No records for the selected period</p></div>';
		return;
	}

	try {
		var chart = new ApexCharts(el, opts);
		chart.render();
		window._hrd.charts[id] = chart;
	} catch (e) {
		console.error('[HRD] chart error ' + id, e);
		el.innerHTML = '<div class="hrd-chart-err">Chart unavailable — check console</div>';
	}
}

function _x(base, extra) { return Object.assign({}, base, extra); }

function _hrd_destroy() {
	Object.values(window._hrd.charts).forEach(function (c) { try { c.destroy(); } catch (e) {} });
	window._hrd.charts = {};
}

function _hrd_loading(wrapper, on) {
	var $m = $(wrapper).find('.layout-main-section');
	if (on) { $m.find('#hrd-content').hide(); $m.find('#hrd-err').hide(); $m.find('#hrd-spin').show(); }
	else    { $m.find('#hrd-spin').hide(); }
}

function _hrd_error(wrapper, msg) {
	var $m = $(wrapper).find('.layout-main-section');
	$m.find('#hrd-spin').hide(); $m.find('#hrd-content').hide();
	$m.find('#hrd-err').text(msg).show();
}

/* ─── HTML ───────────────────────────────────────────────────────────────── */
function _hrd_html() {
	function card(id, title, sub) {
		return '<div class="hrd-card"><div class="hrd-card-hd"><span>' + title +
			'</span><span class="hrd-sub">' + sub + '</span></div>' +
			'<div class="hrd-chart-wrap" id="' + id + '"></div></div>';
	}
	function sec(ico, lbl) {
		return '<div class="hrd-sec"><span class="hrd-sec-dot">' + ico + '</span><span>' + lbl + '</span></div>';
	}
	return '<div class="hrd">' +

	/* Hero */
	'<div class="hrd-hero">' +
		'<div>' +
			'<div class="hrd-eyebrow">HR Analytics Platform</div>' +
			'<h2 class="hrd-h2">HR Dashboard</h2>' +
			'<p class="hrd-hero-p">Attendance · Recruitment · Payroll · Leaves · Lifecycle — all in one view.</p>' +
		'</div>' +
		'<div class="hrd-hero-r">' +
			'<span id="hrd-period" class="hrd-pill"></span>' +
			'<span id="hrd-updated" class="hrd-ts"></span>' +
			'<button id="hrd-btn-refresh" class="hrd-btn">↻ Refresh</button>' +
		'</div>' +
	'</div>' +

	/* Date Filter Bar */
	'<div class="hrd-filters">' +
		'<div class="hrd-filter-label">Date Range</div>' +
		'<div class="hrd-filter-inputs">' +
			'<div class="hrd-filter-group">' +
				'<label class="hrd-flbl">From Date</label>' +
				'<input type="date" id="hrd-from" class="hrd-date-inp">' +
			'</div>' +
			'<div class="hrd-filter-sep">→</div>' +
			'<div class="hrd-filter-group">' +
				'<label class="hrd-flbl">To Date</label>' +
				'<input type="date" id="hrd-to" class="hrd-date-inp">' +
			'</div>' +
			'<button id="hrd-btn-apply" class="hrd-btn-apply">Apply Filter</button>' +
			'<button id="hrd-btn-reset" class="hrd-btn-reset">Reset</button>' +
		'</div>' +
	'</div>' +

	/* Spinner / Error */
	'<div id="hrd-spin" class="hrd-spin"><div class="hrd-spinner"></div><p>Loading dashboard…</p></div>' +
	'<div id="hrd-err" class="hrd-err" style="display:none"></div>' +

	/* Content */
	'<div id="hrd-content" style="display:none">' +
		'<div id="hrd-kpi-strip" class="hrd-kpis"></div>' +

		/* ── ATTENDANCE ── */
		sec('📅', 'Attendance') +
		'<div class="hrd-row hrd-split-2-1">' +
			card('hrd-c-att',        '6-Month Attendance Trend',      'Present · Late · Absent · Early') +
			card('hrd-c-month-donut','Period Summary at a Glance',    'From Employee Attendance monthly records') +
		'</div>' +
		'<div class="hrd-row hrd-cols-2">' +
			card('hrd-c-ot',  'Overtime vs Approved OT',   '6-month area trend in hours') +
			card('hrd-c-lot', 'Late Over Time Requests',   '6-month OT from Late Over Time docs') +
		'</div>' +
		'<div class="hrd-row hrd-cols-2">' +
			card('hrd-c-missing', 'Missing Logs',              'Missed check-in &amp; check-out') +
			card('hrd-c-branch',  'Branch-wise Attendance',    'Present · Late · Absent by Branch/Unit') +
		'</div>' +
		'<div class="hrd-row">' +
			card('hrd-c-desig', 'Designation-wise Attendance', 'Present · Late · Absent by designation · period end month') +
		'</div>' +

		/* ── RECRUITMENT ── */
		sec('💼', 'Recruitment') +
		'<div class="hrd-row hrd-cols-2">' +
			card('hrd-c-funnel',    'Hiring Pipeline',     'Opens → Applicants → Interviews → Offers') +
			card('hrd-c-applicants','Monthly Applicants',  '6-month area trend') +
		'</div>' +
		'<div class="hrd-row">' +
			card('hrd-c-job-dept', 'Open Jobs by Department', 'Current snapshot') +
		'</div>' +

		/* ── PAYROLL ── */
		sec('💰', 'Payroll &amp; Claims') +
		'<div class="hrd-row hrd-cols-2">' +
			card('hrd-c-payroll',  'Salary Slips &amp; Advances',           'Submitted count per month') +
			card('hrd-c-expense',  'Expense Claims &amp; Additional Salary', '6-month trend') +
		'</div>' +

		/* ── LEAVE ── */
		sec('📋', 'Leave') +
		'<div class="hrd-row hrd-cols-2">' +
			card('hrd-c-leave-type',   'Leave by Type',   'Applications by leave type') +
			card('hrd-c-leave-status', 'Leave by Status', 'Approved · Pending · Rejected') +
		'</div>' +
		'<div class="hrd-row">' +
			card('hrd-c-leave-trend', 'Leave Trend', '6-month applications trend') +
		'</div>' +

		/* ── EMPLOYEES ── */
		sec('👥', 'Employee Distribution') +
		'<div class="hrd-row hrd-cols-3">' +
			card('hrd-c-emp-dept', 'Headcount by Department', 'Active employees') +
			card('hrd-c-emp-type', 'Employment Type',          'By contract type') +
			card('hrd-c-gender',   'Gender Distribution',      'Active workforce') +
		'</div>' +

		/* ── LIFECYCLE ── */
		sec('🔄', 'Employee Lifecycle') +
		'<div class="hrd-row hrd-cols-2">' +
			card('hrd-c-lifecycle', 'Joiners vs Relieved',    '6-month comparison') +
			card('hrd-c-dept-perf', 'Department Performance', 'Present % · Late · Absent') +
		'</div>' +

	'</div></div>';
}

/* ─── CSS ────────────────────────────────────────────────────────────────── */
function _hrd_css() {
	return '<style>' +
	'.hrd{font-family:"Space Grotesk","Inter",sans-serif;color:#111827;max-width:1680px;margin:0 auto;padding-bottom:48px}' +

	/* Hero */
	'.hrd-hero{background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 48%,#2563eb 100%);border-radius:22px;padding:28px 34px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;box-shadow:0 20px 48px rgba(37,99,235,.3),inset 0 1px 0 rgba(255,255,255,.1)}' +
	'.hrd-eyebrow{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:rgba(255,255,255,.55);margin-bottom:8px;font-weight:600}' +
	'.hrd-h2{margin:0 0 7px;font-size:30px;font-weight:800;color:#fff;letter-spacing:-.02em;line-height:1.1}' +
	'.hrd-hero-p{margin:0;color:rgba(255,255,255,.7);font-size:13.5px;max-width:540px}' +
	'.hrd-hero-r{display:flex;flex-direction:column;align-items:flex-end;gap:9px}' +
	'.hrd-pill{background:rgba(255,255,255,.14);color:#fff;padding:5px 14px;border-radius:999px;font-size:12px;font-weight:700;border:1px solid rgba(255,255,255,.22)}' +
	'.hrd-ts{color:rgba(255,255,255,.5);font-size:11px}' +
	'.hrd-btn{background:rgba(255,255,255,.14);color:#fff;border:1px solid rgba(255,255,255,.28);border-radius:10px;padding:9px 20px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;transition:background .2s}' +
	'.hrd-btn:hover{background:rgba(255,255,255,.26)}' +

	/* Filter bar */
	'.hrd-filters{background:#fff;border:1px solid #e8ecf5;border-radius:16px;padding:14px 20px;margin-bottom:20px;display:flex;align-items:center;gap:20px;flex-wrap:wrap;box-shadow:0 2px 12px rgba(0,0,0,.045)}' +
	'.hrd-filter-label{font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;flex-shrink:0}' +
	'.hrd-filter-inputs{display:flex;align-items:center;gap:12px;flex-wrap:wrap;flex:1}' +
	'.hrd-filter-group{display:flex;flex-direction:column;gap:3px}' +
	'.hrd-flbl{font-size:11px;color:#9ca3af;font-weight:500}' +
	'.hrd-date-inp{border:1.5px solid #d1d5db;border-radius:9px;padding:7px 12px;font-size:13px;font-family:inherit;color:#111827;background:#f9fafb;outline:none;transition:border-color .18s}' +
	'.hrd-date-inp:focus{border-color:#4361ee;background:#fff}' +
	'.hrd-filter-sep{color:#9ca3af;font-size:18px;font-weight:300;margin-top:14px}' +
	'.hrd-btn-apply{background:#4361ee;color:#fff;border:none;border-radius:10px;padding:9px 20px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;transition:background .2s;margin-top:14px}' +
	'.hrd-btn-apply:hover{background:#3451d1}' +
	'.hrd-btn-reset{background:#f3f4f6;color:#374151;border:1.5px solid #d1d5db;border-radius:10px;padding:9px 16px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;transition:background .2s;margin-top:14px}' +
	'.hrd-btn-reset:hover{background:#e5e7eb}' +

	/* KPI strip */
	'.hrd-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:11px;margin-bottom:28px}' +
	'.hrd-kpi{background:var(--kb,#f0f4ff);border:1px solid rgba(0,0,0,.07);border-radius:16px;padding:14px 15px;display:flex;align-items:center;gap:11px;box-shadow:0 2px 10px rgba(0,0,0,.045);transition:transform .18s,box-shadow .18s;cursor:default}' +
	'.hrd-kpi:hover{transform:translateY(-4px);box-shadow:0 10px 22px rgba(0,0,0,.1)}' +
	'.hrd-kpi-ico{width:40px;height:40px;border-radius:11px;background:rgba(255,255,255,.85);display:grid;place-items:center;font-size:19px;flex-shrink:0;box-shadow:0 2px 7px rgba(0,0,0,.08)}' +
	'.hrd-kpi-val{font-size:20px;font-weight:800;line-height:1}' +
	'.hrd-kpi-lbl{font-size:11px;color:#6b7280;margin-top:3px;font-weight:500;line-height:1.3}' +
	'.hrd-kpi-sub{font-size:10px;color:#9ca3af;margin-top:2px}' +

	/* Section headings */
	'.hrd-sec{display:flex;align-items:center;gap:10px;margin:28px 0 13px;padding-bottom:10px;border-bottom:2px solid #f1f5f9}' +
	'.hrd-sec>span:last-child{font-size:16.5px;font-weight:800;color:#111827;letter-spacing:-.01em}' +
	'.hrd-sec-dot{width:32px;height:32px;border-radius:9px;background:linear-gradient(135deg,#eef2ff,#e0e7ff);display:grid;place-items:center;font-size:16px;box-shadow:0 2px 8px rgba(67,97,238,.18)}' +

	/* Rows & cards */
	'.hrd-row{display:grid;gap:16px;margin-bottom:16px}' +
	'.hrd-cols-2{grid-template-columns:repeat(auto-fit,minmax(370px,1fr))}' +
	'.hrd-cols-3{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}' +
	'.hrd-split-2-1{grid-template-columns:2fr 1fr}' +
	'.hrd-card{background:#fff;border:1px solid #e8ecf5;border-radius:18px;padding:18px 20px;box-shadow:0 3px 18px rgba(17,24,39,.055);overflow:hidden}' +
	'.hrd-card-hd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px;flex-wrap:wrap;gap:5px}' +
	'.hrd-card-hd>span:first-child{font-size:14px;font-weight:700;color:#111827}' +
	'.hrd-sub{font-size:11.5px;color:#9ca3af}' +
	'.hrd-chart-wrap{min-height:260px}' +

	/* No-data state */
	'.hrd-nodata{display:flex;flex-direction:column;align-items:center;justify-content:center;height:220px;color:#9ca3af;gap:10px}' +
	'.hrd-nodata-ico{font-size:36px;opacity:.5}' +
	'.hrd-nodata p{font-size:13px;font-weight:500;margin:0}' +
	'.hrd-chart-err{color:#9ca3af;font-size:13px;text-align:center;padding:50px 0}' +

	/* Loading / error */
	'.hrd-spin{text-align:center;padding:80px 20px;color:#6b7280}' +
	'.hrd-spinner{width:44px;height:44px;border:3.5px solid #e5e7eb;border-top-color:#4361ee;border-radius:50%;animation:hrd-spin .7s linear infinite;margin:0 auto 18px}' +
	'@keyframes hrd-spin{to{transform:rotate(360deg)}}' +
	'.hrd-err{background:#fef2f2;border:1px solid #fecaca;border-radius:14px;padding:18px 22px;color:#991b1b;font-weight:600;margin-bottom:16px}' +

	/* Responsive */
	'@media(max-width:900px){.hrd-split-2-1{grid-template-columns:1fr}}' +
	'@media(max-width:640px){' +
		'.hrd-hero{padding:20px 18px}.hrd-h2{font-size:22px}' +
		'.hrd-kpis{grid-template-columns:repeat(2,1fr)}' +
		'.hrd-cols-2,.hrd-cols-3{grid-template-columns:1fr}' +
		'.hrd-filter-inputs{flex-direction:column;align-items:flex-start}' +
		'.hrd-filter-sep{display:none}' +
		'.hrd-btn-apply,.hrd-btn-reset{margin-top:0}' +
	'}' +
	'</style>';
}
