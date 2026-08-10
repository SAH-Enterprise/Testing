(() => {
	const POLL_MS = 2000;
	const MACHINE_POLL_MS = 15000;
	const FLASH_MS = 4500;
	const seen = new Set();
	let soundEnabled = false;
	let audioCtx = null;
	let since = null;
	let flashTimer = null;
	let bootstrapped = false;
	let lastMachineStatus = null;

	const els = {
		app: document.getElementById("app"),
		brandDot: document.getElementById("brandDot"),
		clock: document.getElementById("clock"),
		enableSound: document.getElementById("enableSound"),
		idleState: document.getElementById("idleState"),
		punchState: document.getElementById("punchState"),
		empImage: document.getElementById("empImage"),
		empFallback: document.getElementById("empFallback"),
		logType: document.getElementById("logType"),
		empName: document.getElementById("empName"),
		empSub: document.getElementById("empSub"),
		punchTime: document.getElementById("punchTime"),
		punchDate: document.getElementById("punchDate"),
		feedList: document.getElementById("feedList"),
		statusText: document.getElementById("statusText"),
		lastSync: document.getElementById("lastSync"),
		integrationBadge: document.getElementById("integrationBadge"),
		machineMeta: document.getElementById("machineMeta"),
		machineList: document.getElementById("machineList"),
	};

	function pad(n) {
		return String(n).padStart(2, "0");
	}

	function tickClock() {
		const d = new Date();
		els.clock.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
	}

	function typeClass(type) {
		const t = String(type || "").toLowerCase();
		if (t.includes("check in") || t === "in") return "check-in";
		if (t.includes("check out") || t === "out") return "check-out";
		return "punch";
	}

	function ensureAudio() {
		if (!audioCtx) {
			const Ctx = window.AudioContext || window.webkitAudioContext;
			if (!Ctx) return null;
			audioCtx = new Ctx();
		}
		if (audioCtx.state === "suspended") {
			audioCtx.resume();
		}
		return audioCtx;
	}

	function playRing() {
		if (!soundEnabled) return;
		const ctx = ensureAudio();
		if (!ctx) return;

		const now = ctx.currentTime;
		[0, 0.18, 0.36].forEach((offset, i) => {
			const osc = ctx.createOscillator();
			const gain = ctx.createGain();
			osc.type = "sine";
			osc.frequency.value = i === 1 ? 980 : 880;
			gain.gain.setValueAtTime(0.0001, now + offset);
			gain.gain.exponentialRampToValueAtTime(0.28, now + offset + 0.02);
			gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.16);
			osc.connect(gain);
			gain.connect(ctx.destination);
			osc.start(now + offset);
			osc.stop(now + offset + 0.18);
		});
	}

	function renderHero(punch) {
		els.idleState.classList.add("hidden");
		els.punchState.classList.remove("hidden");

		els.empName.textContent = punch.employee_name || `ID ${punch.biometric_id || ""}`;
		els.empSub.textContent = [punch.designation, punch.department, punch.biometric_id]
			.filter(Boolean)
			.join(" · ");
		els.punchTime.textContent = punch.attendance_time || "--:--:--";
		els.punchDate.textContent = punch.attendance_date || "";
		els.logType.textContent = punch.type || "Punch";
		els.logType.className = `pp-type-badge ${typeClass(punch.type)}`;

		const initial = avatarInitial(punch);
		if (punch.image) {
			els.empImage.src = punch.image;
			els.empImage.classList.add("visible");
			els.empFallback.classList.add("hidden");
			els.empImage.onerror = () => {
				els.empImage.classList.remove("visible");
				els.empFallback.classList.remove("hidden");
				els.empFallback.textContent = initial;
			};
		} else {
			els.empImage.removeAttribute("src");
			els.empImage.classList.remove("visible");
			els.empFallback.classList.remove("hidden");
			els.empFallback.textContent = initial;
		}
	}

	function avatarInitial(punch) {
		const name = String(punch.employee_name || "").trim();
		if (name && !/^ID\s*\d+/i.test(name)) {
			return name.slice(0, 1).toUpperCase();
		}
		const bio = String(punch.biometric_id || "").trim();
		return bio ? bio.slice(-2) : "?";
	}

	function showPunch(punch, { announce = true, addFeed = true } = {}) {
		if (!punch || !punch.name) return;
		if (seen.has(punch.name)) return;
		seen.add(punch.name);

		renderHero(punch);
		if (addFeed) prependFeed(punch);

		if (announce) {
			els.app.classList.add("flash-green");
			playRing();
			if (flashTimer) clearTimeout(flashTimer);
			flashTimer = setTimeout(() => els.app.classList.remove("flash-green"), FLASH_MS);
		}
	}

	function prependFeed(punch, { trim = true } = {}) {
		try {
			const li = document.createElement("li");
			li.className = "pp-feed-item";
			li.dataset.punch = punch.name || "";
			const initial = avatarInitial(punch);
			const name = escapeHtml(punch.employee_name || "");
			const type = escapeHtml(punch.type || "Punch");
			const date = escapeHtml(punch.attendance_date || "");
			const time = escapeHtml(punch.attendance_time || "");
			const img = punch.image
				? `<img src="${escapeHtml(punch.image)}" alt="" />`
				: `<div class="pp-feed-avatar">${escapeHtml(initial)}</div>`;
			li.innerHTML = `
				${img}
				<div>
					<div class="pp-feed-name">${name}</div>
					<div class="pp-feed-detail">${type} · ${date}</div>
				</div>
				<div class="pp-feed-time">${time}</div>
			`;
			const imgEl = li.querySelector("img");
			if (imgEl) {
				imgEl.onerror = () => {
					const fallback = document.createElement("div");
					fallback.className = "pp-feed-avatar";
					fallback.textContent = initial;
					imgEl.replaceWith(fallback);
				};
			}
			els.feedList.prepend(li);
			if (trim) {
				while (els.feedList.children.length > 60) {
					els.feedList.removeChild(els.feedList.lastChild);
				}
			}
		} catch (err) {
			console.error("feed item failed", punch && punch.name, err);
		}
	}

	function rebuildFeed(punches) {
		els.feedList.innerHTML = "";
		// punches are oldest→newest; prepend so newest ends on top
		punches.forEach((punch) => {
			if (!punch || !punch.name || seen.has(punch.name)) return;
			seen.add(punch.name);
			prependFeed(punch, { trim: false });
		});
		while (els.feedList.children.length > 60) {
			els.feedList.removeChild(els.feedList.lastChild);
		}
		els.feedList.scrollTop = 0;
	}

	function escapeHtml(value) {
		return String(value)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;");
	}

	function formatCheckedAt(value) {
		if (!value) return "";
		try {
			return new Date(value.replace(" ", "T")).toLocaleTimeString();
		} catch (e) {
			return value;
		}
	}

	function renderMachineStatus(status) {
		if (!status || !els.integrationBadge || !els.machineList) return;
		lastMachineStatus = status;
		const integrated = !!status.integrated;
		const partial = !!status.partial;
		const onlineCount = status.online_count || 0;
		const total = status.total_count || (status.machines || []).length;

		els.integrationBadge.textContent = status.status_label || "Not integrated with machines";
		els.integrationBadge.className = "pp-integration-badge";
		if (integrated) {
			els.integrationBadge.classList.add("integrated");
		} else if (partial || onlineCount > 0) {
			els.integrationBadge.classList.add("partial");
		} else {
			els.integrationBadge.classList.add("offline");
		}

		els.brandDot.classList.remove("online", "offline");
		els.brandDot.classList.add(integrated || onlineCount > 0 ? "online" : "offline");

		const checked = formatCheckedAt(status.machine_checked_at);
		els.machineMeta.textContent = [
			`${onlineCount}/${total} online`,
			status.source === "live_sync" ? "from machine sync" : "TCP check only",
			checked ? `checked ${checked}` : "",
		]
			.filter(Boolean)
			.join(" · ");

		els.machineList.innerHTML = "";
		(status.machines || []).forEach((m) => {
			const chip = document.createElement("div");
			const isUp = !!(m.integrated || m.online);
			chip.className = `pp-machine-chip ${isUp ? "online" : "offline"}${
				m.integrated ? " integrated" : ""
			}`;
			const label = `${m.type || "Machine"} ${m.ip}:${m.port}`;
			const state = m.integrated ? "Integrated" : m.online ? "Reachable" : "Offline";
			chip.innerHTML = `
				<span class="dot"></span>
				<span><strong>${escapeHtml(label)}</strong> · ${escapeHtml(state)}</span>
				${m.error && !isUp ? `<span class="err">${escapeHtml(m.error)}</span>` : ""}
			`;
			els.machineList.appendChild(chip);
		});

		if (!(status.machines || []).length) {
			els.machineList.innerHTML =
				'<div class="pp-machine-chip offline"><span class="dot"></span><span>No machines configured in V HR Settings</span></div>';
		}
	}

	function updateFooterStatus() {
		if (!els.statusText || !els.lastSync) return;
		const ms = lastMachineStatus;
		if (!ms) {
			els.statusText.textContent = "Checking machine integration…";
			els.lastSync.textContent = `Portal refreshed ${new Date().toLocaleTimeString()}`;
			return;
		}
		if (ms.integrated) {
			els.statusText.textContent = soundEnabled
				? "Machines integrated · Sound on"
				: "Machines integrated · Tap Enable Sound";
		} else if (ms.partial || (ms.online_count || 0) > 0) {
			els.statusText.textContent = "Machines reachable - not fully integrated";
		} else {
			els.statusText.textContent = "Not integrated with machines";
		}
		// Honest wording: portal refresh is not machine sync
		els.lastSync.textContent = `Portal refreshed ${new Date().toLocaleTimeString()}`;
	}

	async function apiGet(method, args = {}) {
		const params = new URLSearchParams();
		Object.entries(args).forEach(([key, value]) => {
			if (value !== undefined && value !== null && value !== "") {
				params.set(key, value);
			}
		});
		const qs = params.toString();
		const res = await fetch(`/api/method/${method}${qs ? `?${qs}` : ""}`, {
			credentials: "same-origin",
			headers: { Accept: "application/json" },
		});
		const data = await res.json();
		if (!res.ok || data.exc) {
			throw new Error((data._server_messages && data._server_messages) || data.exc || "API error");
		}
		return data.message;
	}

	async function pollMachines() {
		try {
			const status = await apiGet(
				"hr_vfg.hr_ventureforce_global.punch_portal.get_machine_status",
				{ force: 0 }
			);
			renderMachineStatus(status);
			updateFooterStatus();
		} catch (err) {
			els.integrationBadge.textContent = "Machine status unavailable";
			els.integrationBadge.className = "pp-integration-badge offline";
			els.statusText.textContent = "Cannot check machine integration";
			console.error(err);
		}
	}

	async function poll() {
		try {
			const payload = await apiGet(
				"hr_vfg.hr_ventureforce_global.punch_portal.get_latest_punches",
				{
					since: since || "",
					limit: bootstrapped ? 40 : 50,
				}
			);
			const punches = payload.punches || [];

			if (payload.machine_status) {
				renderMachineStatus(payload.machine_status);
			}

			if (!bootstrapped) {
				rebuildFeed(punches);
				if (punches.length) {
					renderHero(punches[punches.length - 1]);
				}
				bootstrapped = true;
			} else {
				punches.forEach((punch) => showPunch(punch, { announce: true }));
				// Keep newest punches visible after live prepends
				if (punches.length) {
					els.feedList.scrollTop = 0;
				}
			}

			since = payload.server_time || since;
			updateFooterStatus();
		} catch (err) {
			els.statusText.textContent = "Portal reconnecting…";
			console.error(err);
		}
	}

	els.enableSound.addEventListener("click", () => {
		soundEnabled = true;
		ensureAudio();
		playRing();
		els.enableSound.textContent = "Sound On";
		els.enableSound.classList.add("enabled");
		updateFooterStatus();
	});

	if ("serviceWorker" in navigator) {
		// Drop old cached portal SW that kept showing "Synced" without machine status.
		navigator.serviceWorker.getRegistrations().then((regs) => {
			Promise.all(regs.map((r) => r.unregister())).finally(() => {
				navigator.serviceWorker
					.register("/assets/hr_vfg/punch_portal/sw.js?v=5")
					.then((reg) => reg.update())
					.catch(() => {});
			});
		});
		if (window.caches && caches.keys) {
			caches.keys().then((keys) =>
				Promise.all(keys.filter((k) => k.startsWith("punch-portal")).map((k) => caches.delete(k)))
			);
		}
	}

	tickClock();
	setInterval(tickClock, 1000);
	pollMachines();
	poll();
	setInterval(poll, POLL_MS);
	setInterval(pollMachines, MACHINE_POLL_MS);
})();
