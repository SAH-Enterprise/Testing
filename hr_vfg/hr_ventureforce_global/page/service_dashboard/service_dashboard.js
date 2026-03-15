frappe.pages['service-dashboard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Service Dashboard',
		single_column: true,
	});

	const $wrapper = $(wrapper).find('.layout-main-section');
	$wrapper.empty();

	$wrapper.append(`
		<style>
			.service-dashboard {
				--sd-bg: #f7f6f2;
				--sd-card: #ffffff;
				--sd-ink: #1b1b1b;
				--sd-muted: #6b6b6b;
				--sd-accent: #1f7a5c;
				--sd-accent-2: #b1522f;
				--sd-accent-3: #2f5d9f;
				--sd-border: #e6e1d9;
				font-family: 'Space Grotesk', 'Inter', sans-serif;
				font-size: 14px;
				width: 100%;
				max-width: 1600px;
				margin: 0 auto;
			}
			.service-dashboard .sd-hero {
				background: linear-gradient(135deg, #efe9df, #f7f6f2);
				border: 1px solid var(--sd-border);
				border-radius: 16px;
				padding: 18px 20px;
				margin-bottom: 16px;
			}
			.service-dashboard .sd-hero h3 {
				margin: 0 0 6px 0;
				color: var(--sd-ink);
				font-weight: 600;
			}
			.service-dashboard .sd-hero p {
				margin: 0;
				color: var(--sd-muted);
			}
			.service-dashboard .sd-filters {
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
				gap: 12px;
				align-items: end;
				margin-top: 12px;
			}
			.service-dashboard .sd-grid {
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
				gap: 12px;
				margin: 16px 0;
			}
			.service-dashboard .sd-card {
				background: var(--sd-card);
				border: 1px solid var(--sd-border);
				border-radius: 14px;
				padding: 14px 16px;
				box-shadow: 0 2px 10px rgba(0,0,0,0.04);
			}
			.service-dashboard .sd-card h4 {
				margin: 0 0 6px 0;
				font-size: 12px;
				text-transform: uppercase;
				letter-spacing: 0.04em;
				color: var(--sd-muted);
			}
			.service-dashboard .sd-card .sd-value {
				font-size: 22px;
				font-weight: 600;
				color: var(--sd-ink);
			}
			.service-dashboard .sd-charts {
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
				gap: 16px;
				margin-bottom: 20px;
			}
			.service-dashboard .sd-chart {
				background: var(--sd-card);
				border: 1px solid var(--sd-border);
				border-radius: 16px;
				padding: 12px 14px;
			}
			.service-dashboard .sd-chart h5 {
				margin: 0 0 6px 0;
				font-size: 15px;
				color: var(--sd-ink);
			}
			.service-dashboard .sd-chart .sd-chart-body {
				min-height: 320px;
			}
			.service-dashboard .sd-tables {
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
				gap: 16px;
			}
			.service-dashboard table {
				width: 100%;
				border-collapse: collapse;
				font-size: 13px;
			}
			.service-dashboard th,
			.service-dashboard td {
				border-bottom: 1px solid var(--sd-border);
				padding: 6px 8px;
				text-align: left;
			}
			.service-dashboard th {
				color: var(--sd-muted);
				font-weight: 600;
				text-transform: uppercase;
				font-size: 11px;
			}
			@media (max-width: 640px) {
				.service-dashboard .sd-hero {
					padding: 14px;
				}
			}
		</style>
		<div class="service-dashboard">
			<div class="sd-hero">
				<h3>Service Overview</h3>
				<p>Comprehensive view of Service Billing and Meal Form activity.</p>
				<div class="sd-filters">
					<div>
						<label class="form-label">From Date</label>
						<input type="date" class="form-control" id="sd-from-date" />
					</div>
					<div>
						<label class="form-label">To Date</label>
						<input type="date" class="form-control" id="sd-to-date" />
					</div>
					<div>
						<label class="form-label">Service Provider</label>
						<select class="form-control" id="sd-service-provider"></select>
					</div>
					<div>
						<label class="form-label">Contractor</label>
						<select class="form-control" id="sd-contractor"></select>
					</div>
					<div>
						<label class="form-label">Service Type</label>
						<select class="form-control" id="sd-service-type"></select>
					</div>
					<div>
						<label class="form-label">Billed</label>
						<select class="form-control" id="sd-billed">
							<option value="">All</option>
							<option value="Billed">Billed</option>
							<option value="Not Billed">Not Billed</option>
						</select>
					</div>
					<div>
						<label class="form-label">Invoiced</label>
						<select class="form-control" id="sd-invoiced">
							<option value="">All</option>
							<option value="Invoiced">Invoiced</option>
							<option value="Not Invoiced">Not Invoiced</option>
						</select>
					</div>
					<div>
						<label class="form-label">Trend</label>
						<select class="form-control" id="sd-granularity">
							<option value="Daily">Daily</option>
							<option value="Weekly">Weekly</option>
							<option value="Monthly">Monthly</option>
						</select>
					</div>
					<button class="btn btn-primary" id="sd-refresh">Refresh</button>
				</div>
			</div>
			<div class="sd-grid" id="sd-kpis"></div>
			<div class="sd-charts">
				<div class="sd-chart"><h5>Service Billing Amount Trend</h5><div class="sd-chart-body" id="sd-billing-trend"></div></div>
				<div class="sd-chart"><h5>Meal Form Amount Trend</h5><div class="sd-chart-body" id="sd-meal-trend"></div></div>
				<div class="sd-chart"><h5>Service Detail Amount Trend</h5><div class="sd-chart-body" id="sd-service-trend"></div></div>
				<div class="sd-chart"><h5>Billing vs Service Detail Split</h5><div class="sd-chart-body" id="sd-billing-split"></div></div>
				<div class="sd-chart"><h5>Top Service Providers</h5><div class="sd-chart-body" id="sd-top-providers"></div></div>
				<div class="sd-chart"><h5>Top Contractors</h5><div class="sd-chart-body" id="sd-top-contractors"></div></div>
				<div class="sd-chart"><h5>Meal Types by Amount</h5><div class="sd-chart-body" id="sd-meal-type"></div></div>
				<div class="sd-chart"><h5>Service Detail by Item</h5><div class="sd-chart-body" id="sd-item-detail"></div></div>
				<div class="sd-chart"><h5>Qty vs Amount (Meal Forms)</h5><div class="sd-chart-body" id="sd-scatter"></div></div>

				<div class="sd-chart"><h5>Meal Form Qty Trend</h5><div class="sd-chart-body" id="sd-meal-qty"></div></div>
				<div class="sd-chart"><h5>Service Billing Qty Trend</h5><div class="sd-chart-body" id="sd-billing-qty"></div></div>
				<div class="sd-chart"><h5>Avg Rate Trend (Service Billing)</h5><div class="sd-chart-body" id="sd-avg-rate"></div></div>
				<div class="sd-chart"><h5>Service Provider by Type</h5><div class="sd-chart-body" id="sd-provider-type"></div></div>
				<div class="sd-chart"><h5>Contractor by Type</h5><div class="sd-chart-body" id="sd-contractor-type"></div></div>
				<div class="sd-chart"><h5>Meal Provider Amount</h5><div class="sd-chart-body" id="sd-meal-provider"></div></div>
				<div class="sd-chart"><h5>Department Amount</h5><div class="sd-chart-body" id="sd-department"></div></div>
				<div class="sd-chart"><h5>Cost Center Amount</h5><div class="sd-chart-body" id="sd-cost-center"></div></div>
				<div class="sd-chart"><h5>Top Items by Qty</h5><div class="sd-chart-body" id="sd-top-items-qty"></div></div>
				<div class="sd-chart"><h5>Top Items by Amount</h5><div class="sd-chart-body" id="sd-top-items-amount"></div></div>
				<div class="sd-chart"><h5>Top Meal Types by Qty</h5><div class="sd-chart-body" id="sd-top-meal-qty"></div></div>
				<div class="sd-chart"><h5>Top Meal Types by Amount</h5><div class="sd-chart-body" id="sd-top-meal-amount"></div></div>
				<div class="sd-chart"><h5>Billed vs Not Billed</h5><div class="sd-chart-body" id="sd-billed"></div></div>
				<div class="sd-chart"><h5>Invoiced vs Not Invoiced</h5><div class="sd-chart-body" id="sd-invoiced"></div></div>
				<div class="sd-chart"><h5>PI Amount Trend</h5><div class="sd-chart-body" id="sd-pi-amount"></div></div>
				<div class="sd-chart"><h5>PI Avg Amount Trend</h5><div class="sd-chart-body" id="sd-pi-avg"></div></div>
				<div class="sd-chart"><h5>Service Billing by Day</h5><div class="sd-chart-body" id="sd-sb-day"></div></div>
				<div class="sd-chart"><h5>Meal Form by Day</h5><div class="sd-chart-body" id="sd-mf-day"></div></div>
				<div class="sd-chart"><h5>Lead Time (Days)</h5><div class="sd-chart-body" id="sd-lead"></div></div>
			</div>
			<div class="sd-tables">
				<div class="sd-card"><h4>Service Billing (Latest)</h4><div id="sd-service-billing-table"></div></div>
				<div class="sd-card"><h4>Meal Forms (Latest)</h4><div id="sd-meal-form-table"></div></div>
				<div class="sd-card"><h4>Service Detail (Latest)</h4><div id="sd-service-detail-table"></div></div>
				<div class="sd-card"><h4>Summary (Latest)</h4><div id="sd-summary-table"></div></div>
			</div>
		</div>
	`);

	let charts = {};

	const load_apexcharts = () => {
		return new Promise((resolve) => {
			if (window.ApexCharts) {
				resolve();
				return;
			}
			const script = document.createElement('script');
			script.src = 'https://cdn.jsdelivr.net/npm/apexcharts@3.49.1/dist/apexcharts.min.js';
			script.onload = () => resolve();
			document.head.appendChild(script);
		});
	};

	const formatCurrency = (value) => frappe.format(value || 0, { fieldtype: 'Currency' });
	const formatFloat = (value) => frappe.format(value || 0, { fieldtype: 'Float' });

	const render_kpis = (data) => {
		const invoicedCount = data.service_billing_stats.invoiced_count || 0;
		const totalBills = data.service_billing_stats.total_bills || 0;
		const pendingInvoice = totalBills - invoicedCount;
		const avgRate = data.service_billing_stats.total_qty
			? (data.service_billing_stats.total_amount || 0) / data.service_billing_stats.total_qty
			: 0;
		const topProvider = data.top_providers?.[0]?.service_provider || '-';
		const topContractor = data.top_contractors?.[0]?.contractor || '-';

		const kpis = [
			{ label: 'Service Billing Amount', value: formatCurrency(data.service_billing_stats.total_amount) },
			{ label: 'Service Detail Amount', value: formatCurrency(data.service_billing_stats.total_service_amount) },
			{ label: 'Meal Form Amount', value: formatCurrency(data.meal_form_stats.total_amount) },
			{ label: 'Total Qty', value: formatFloat((data.service_billing_stats.total_qty || 0) + (data.meal_form_stats.total_qty || 0)) },
			{ label: 'Avg Rate / Qty', value: formatCurrency(avgRate) },
			{ label: 'Service Bills', value: totalBills },
			{ label: 'Invoiced', value: invoicedCount },
			{ label: 'Pending Invoice', value: pendingInvoice },
			{ label: 'Top Provider', value: topProvider },
			{ label: 'Top Contractor', value: topContractor },
			{ label: 'Billed %', value: totalBills ? `${Math.round((invoicedCount / totalBills) * 100)}%` : '0%' },
			{ label: 'Service Detail Qty', value: formatFloat((data.service_detail_qty_trend || []).reduce((s, r) => s + (r.qty || 0), 0)) },
		];

		const $kpis = $('#sd-kpis');
		$kpis.empty();
		kpis.forEach((kpi) => {
			$kpis.append(`<div class="sd-card"><h4>${kpi.label}</h4><div class="sd-value">${kpi.value}</div></div>`);
		});
	};

	const render_chart = (id, options) => {
		if (charts[id]) {
			charts[id].destroy();
		}
		charts[id] = new ApexCharts(document.querySelector(id), options);
		charts[id].render();
	};

	const render_table = (id, columns, rows) => {
		const $target = $(id);
		if (!rows || !rows.length) {
			$target.html('<div class="text-muted">No data</div>');
			return;
		}
		const header = `<tr>${columns.map((c) => `<th>${c.label}</th>`).join('')}</tr>`;
		const body = rows
			.map((row) =>
				`<tr>${columns.map((c) => `<td>${row[c.field] ?? ''}</td>`).join('')}</tr>`
			)
			.join('');
		$target.html(`<table><thead>${header}</thead><tbody>${body}</tbody></table>`);
	};

	const buildStackedSeries = (rows, categoryField, seriesField, valueField) => {
		const categories = Array.from(new Set(rows.map((r) => r[categoryField]).filter(Boolean)));
		const seriesKeys = Array.from(new Set(rows.map((r) => r[seriesField]).filter(Boolean)));
		const series = seriesKeys.map((key) => ({
			name: key,
			data: categories.map((cat) => {
				const match = rows.find((r) => r[categoryField] === cat && r[seriesField] === key);
				return match ? match[valueField] || 0 : 0;
			}),
		}));
		return { categories, series };
	};

	const render_charts = (data) => {
		const billingTrend = {
			series: [{ name: 'Amount', data: data.service_billing_trend.map((row) => row.amount || 0) }],
			chart: { type: 'area', height: 320, toolbar: { show: false } },
			colors: ['#1f7a5c'],
			dataLabels: { enabled: false },
			stroke: { curve: 'smooth', width: 3 },
			xaxis: { categories: data.service_billing_trend.map((row) => row.date) },
			fill: { opacity: 0.2 },
		};

		const mealTrend = {
			series: [{ name: 'Amount', data: data.meal_form_trend.map((row) => row.amount || 0) }],
			chart: { type: 'line', height: 320, toolbar: { show: false } },
			colors: ['#b1522f'],
			dataLabels: { enabled: false },
			stroke: { curve: 'straight', width: 2 },
			xaxis: { categories: data.meal_form_trend.map((row) => row.date) },
		};

		const serviceTrend = {
			series: [{ name: 'Amount', data: data.service_detail_trend.map((row) => row.amount || 0) }],
			chart: { type: 'area', height: 320, toolbar: { show: false } },
			colors: ['#2f5d9f'],
			dataLabels: { enabled: false },
			stroke: { curve: 'smooth', width: 2 },
			xaxis: { categories: data.service_detail_trend.map((row) => row.date) },
			fill: { opacity: 0.2 },
		};

		const split = {
			series: [data.service_billing_stats.total_amount || 0, data.service_billing_stats.total_service_amount || 0],
			labels: ['Billing Total', 'Service Detail Total'],
			chart: { type: 'donut', height: 320 },
			colors: ['#1f7a5c', '#b1522f'],
		};

		const topProviders = {
			series: [{ name: 'Amount', data: data.top_providers.map((row) => row.amount || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			colors: ['#1f7a5c'],
			plotOptions: { bar: { borderRadius: 6, horizontal: true } },
			xaxis: { categories: data.top_providers.map((row) => row.service_provider || 'Unknown') },
		};

		const topContractors = {
			series: [{ name: 'Amount', data: data.top_contractors.map((row) => row.amount || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			colors: ['#b1522f'],
			plotOptions: { bar: { borderRadius: 6, horizontal: true } },
			xaxis: { categories: data.top_contractors.map((row) => row.contractor || 'Unknown') },
		};

		const byType = {
			series: [{ name: 'Amount', data: data.meal_form_by_type.map((row) => row.amount || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			colors: ['#2f5d9f'],
			plotOptions: { bar: { borderRadius: 6, horizontal: true } },
			xaxis: { categories: data.meal_form_by_type.map((row) => row.meal_type || 'Unknown') },
		};

		const itemDetail = {
			series: [{ name: 'Amount', data: data.service_detail_by_item.map((row) => row.amount || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			colors: ['#4a7c59'],
			plotOptions: { bar: { borderRadius: 6, horizontal: true } },
			xaxis: { categories: data.service_detail_by_item.map((row) => row.item || 'Unknown') },
		};

		const scatter = {
			series: [
				{
					name: 'Meal Forms',
					data: data.meal_form_scatter.map((row) => ({ x: row.x || 0, y: row.y || 0, name: row.name })),
				},
			],
			chart: { type: 'scatter', height: 320, toolbar: { show: false }, zoom: { enabled: false } },
			xaxis: { title: { text: 'Qty' } },
			yaxis: { title: { text: 'Amount' } },
			tooltip: {
				custom: ({ seriesIndex, dataPointIndex, w }) => {
					const point = w.config.series[seriesIndex].data[dataPointIndex];
					return `<div class="p-2">${point.name}<br/>Qty: ${point.x}<br/>Amount: ${formatCurrency(point.y)}</div>`;
				},
			},
		};

		const mealQty = {
			series: [{ name: 'Qty', data: data.meal_form_qty_trend.map((row) => row.qty || 0) }],
			chart: { type: 'area', height: 320, toolbar: { show: false } },
			colors: ['#2f5d9f'],
			xaxis: { categories: data.meal_form_qty_trend.map((row) => row.date) },
		};

		const billingQty = {
			series: [{ name: 'Qty', data: data.service_billing_qty_trend.map((row) => row.qty || 0) }],
			chart: { type: 'area', height: 320, toolbar: { show: false } },
			colors: ['#1f7a5c'],
			xaxis: { categories: data.service_billing_qty_trend.map((row) => row.date) },
		};

		const avgRate = {
			series: [{ name: 'Avg Rate', data: data.service_billing_avg_rate_trend.map((row) => row.avg_rate || 0) }],
			chart: { type: 'line', height: 320, toolbar: { show: false } },
			colors: ['#b1522f'],
			xaxis: { categories: data.service_billing_avg_rate_trend.map((row) => row.date) },
		};

		const providerStack = buildStackedSeries(data.provider_by_type, 'service_provider', 'service_type', 'amount');
		const providerByType = {
			series: providerStack.series,
			chart: { type: 'bar', stacked: true, height: 320, toolbar: { show: false } },
			xaxis: { categories: providerStack.categories },
		};

		const contractorStack = buildStackedSeries(data.contractor_by_type, 'contractor', 'service_type', 'amount');
		const contractorByType = {
			series: contractorStack.series,
			chart: { type: 'bar', stacked: true, height: 320, toolbar: { show: false } },
			xaxis: { categories: contractorStack.categories },
		};

		const mealProvider = {
			series: [{ name: 'Amount', data: data.meal_provider_amount.map((row) => row.amount || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			plotOptions: { bar: { borderRadius: 6, horizontal: true } },
			xaxis: { categories: data.meal_provider_amount.map((row) => row.meal_provider || 'Unknown') },
		};

		const department = {
			series: [{ name: 'Amount', data: data.department_amount.map((row) => row.amount || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			plotOptions: { bar: { borderRadius: 6, horizontal: true } },
			xaxis: { categories: data.department_amount.map((row) => row.department || 'Unknown') },
		};

		const costCenter = {
			series: [{ name: 'Amount', data: data.cost_center_amount.map((row) => row.amount || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			plotOptions: { bar: { borderRadius: 6, horizontal: true } },
			xaxis: { categories: data.cost_center_amount.map((row) => row.cost_center || 'Unknown') },
		};

		const topItemsQty = {
			series: [{ name: 'Qty', data: data.top_items_qty.map((row) => row.qty || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			plotOptions: { bar: { borderRadius: 6, horizontal: true } },
			xaxis: { categories: data.top_items_qty.map((row) => row.item || 'Unknown') },
		};

		const topItemsAmount = {
			series: [{ name: 'Amount', data: data.top_items_amount.map((row) => row.amount || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			plotOptions: { bar: { borderRadius: 6, horizontal: true } },
			xaxis: { categories: data.top_items_amount.map((row) => row.item || 'Unknown') },
		};

		const topMealQty = {
			series: [{ name: 'Qty', data: data.top_meal_types_qty.map((row) => row.qty || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			plotOptions: { bar: { borderRadius: 6, horizontal: true } },
			xaxis: { categories: data.top_meal_types_qty.map((row) => row.meal_type || 'Unknown') },
		};

		const topMealAmount = {
			series: [{ name: 'Amount', data: data.top_meal_types_amount.map((row) => row.amount || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			plotOptions: { bar: { borderRadius: 6, horizontal: true } },
			xaxis: { categories: data.top_meal_types_amount.map((row) => row.meal_type || 'Unknown') },
		};

		const billedSplit = {
			series: [data.billed_split.billed || 0, data.billed_split.not_billed || 0],
			labels: ['Billed', 'Not Billed'],
			chart: { type: 'donut', height: 320 },
		};

		const invoicedSplit = {
			series: [data.invoiced_split.invoiced || 0, data.invoiced_split.not_invoiced || 0],
			labels: ['Invoiced', 'Not Invoiced'],
			chart: { type: 'donut', height: 320 },
		};

		const piAmount = {
			series: [{ name: 'Amount', data: data.pi_amount_trend.map((row) => row.amount || 0) }],
			chart: { type: 'area', height: 320, toolbar: { show: false } },
			colors: ['#1f7a5c'],
			xaxis: { categories: data.pi_amount_trend.map((row) => row.date) },
		};

		const piAvg = {
			series: [{ name: 'Avg Amount', data: data.pi_avg_trend.map((row) => row.avg_amount || 0) }],
			chart: { type: 'line', height: 320, toolbar: { show: false } },
			colors: ['#b1522f'],
			xaxis: { categories: data.pi_avg_trend.map((row) => row.date) },
		};

		const sbDay = {
			series: [{ name: 'Count', data: data.sb_by_day.map((row) => row.count || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			xaxis: { categories: data.sb_by_day.map((row) => row.day || 'Unknown') },
		};

		const mfDay = {
			series: [{ name: 'Count', data: data.mf_by_day.map((row) => row.count || 0) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			xaxis: { categories: data.mf_by_day.map((row) => row.day || 'Unknown') },
		};

		const lead = {
			series: [{ name: 'Count', data: Object.values(data.lead_time_buckets || {}) }],
			chart: { type: 'bar', height: 320, toolbar: { show: false } },
			xaxis: { categories: Object.keys(data.lead_time_buckets || {}) },
		};

		render_chart('#sd-billing-trend', billingTrend);
		render_chart('#sd-meal-trend', mealTrend);
		render_chart('#sd-service-trend', serviceTrend);
		render_chart('#sd-billing-split', split);
		render_chart('#sd-top-providers', topProviders);
		render_chart('#sd-top-contractors', topContractors);
		render_chart('#sd-meal-type', byType);
		render_chart('#sd-item-detail', itemDetail);
		render_chart('#sd-scatter', scatter);
		render_chart('#sd-meal-qty', mealQty);
		render_chart('#sd-billing-qty', billingQty);
		render_chart('#sd-avg-rate', avgRate);
		render_chart('#sd-provider-type', providerByType);
		render_chart('#sd-contractor-type', contractorByType);
		render_chart('#sd-meal-provider', mealProvider);
		render_chart('#sd-department', department);
		render_chart('#sd-cost-center', costCenter);
		render_chart('#sd-top-items-qty', topItemsQty);
		render_chart('#sd-top-items-amount', topItemsAmount);
		render_chart('#sd-top-meal-qty', topMealQty);
		render_chart('#sd-top-meal-amount', topMealAmount);
		render_chart('#sd-billed', billedSplit);
		render_chart('#sd-invoiced', invoicedSplit);
		render_chart('#sd-pi-amount', piAmount);
		render_chart('#sd-pi-avg', piAvg);
		render_chart('#sd-sb-day', sbDay);
		render_chart('#sd-mf-day', mfDay);
		render_chart('#sd-lead', lead);
	};

	const render_tables = (data) => {
		render_table('#sd-service-billing-table', [
			{ field: 'name', label: 'Service Billing' },
			{ field: 'posting_date', label: 'Date' },
			{ field: 'service_provider', label: 'Provider' },
			{ field: 'service_type', label: 'Type' },
			{ field: 'contractor', label: 'Contractor' },
			{ field: 'total_amount', label: 'Amount' },
		], data.service_billing_list);

		render_table('#sd-meal-form-table', [
			{ field: 'name', label: 'Meal Form' },
			{ field: 'date', label: 'Date' },
			{ field: 'meal_type', label: 'Type' },
			{ field: 'meal_provider', label: 'Provider' },
			{ field: 'total_amount', label: 'Amount' },
		], data.meal_form_list);

		render_table('#sd-service-detail-table', [
			{ field: 'meal_form', label: 'Meal Form' },
			{ field: 'meal_type', label: 'Type' },
			{ field: 'date', label: 'Date' },
			{ field: 'item', label: 'Item' },
			{ field: 'qty', label: 'Qty' },
			{ field: 'amount', label: 'Amount' },
		], data.service_detail_list);

		render_table('#sd-summary-table', [
			{ field: 'service_billing', label: 'Service Billing' },
			{ field: 'item', label: 'Item' },
			{ field: 'qty', label: 'Qty' },
			{ field: 'rate', label: 'Rate' },
			{ field: 'amount', label: 'Amount' },
		], data.summary_list);
	};

	const populate_filters = (filters) => {
		const fill = (id, items) => {
			const $el = $(id);
			$el.empty();
			$el.append('<option value="">All</option>');
			(items || []).forEach((row) => {
				$el.append(`<option value="${row.name}">${row.name}</option>`);
			});
		};
		fill('#sd-service-provider', filters.service_providers);
		fill('#sd-contractor', filters.contractors);
		fill('#sd-service-type', filters.service_types);
	};

	const refresh = () => {
		const from_date = $('#sd-from-date').val();
		const to_date = $('#sd-to-date').val();
		const args = {
			from_date,
			to_date,
			service_provider: $('#sd-service-provider').val(),
			contractor: $('#sd-contractor').val(),
			service_type: $('#sd-service-type').val(),
			billed: $('#sd-billed').val(),
			invoiced: $('#sd-invoiced').val(),
			granularity: $('#sd-granularity').val(),
		};
		frappe.call({
			method: 'hr_vfg.hr_ventureforce_global.page.service_dashboard.service_dashboard.get_dashboard_data',
			args,
			callback: (r) => {
				const data = r.message || {};
				$('#sd-from-date').val(data.from_date);
				$('#sd-to-date').val(data.to_date);
				if (!$('#sd-service-provider option').length && data.filters) {
					populate_filters(data.filters);
				}
				render_kpis(data);
				render_charts(data);
				render_tables(data);
			},
		});
	};

	load_apexcharts().then(() => {
		$('#sd-refresh').on('click', refresh);
		refresh();
	});
};
