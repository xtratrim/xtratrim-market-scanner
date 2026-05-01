const scanButton = document.querySelector("#scanButton");
const premarketButton = document.querySelector("#premarketButton");
const cryptoButton = document.querySelector("#cryptoButton");
const statusEl = document.querySelector("#status");
const REQUEST_TIMEOUT_MS = 120000;
const signalsByKey = new Map();
let activeSetup = null;

const fmtMoney = (value) => {
  if (value === null || value === undefined) return "n/a";
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(2)}K`;
  if (value < 1) return `$${Number(value).toPrecision(4)}`;
  return `$${Number(value).toFixed(2)}`;
};

const fmtPct = (value) => {
  if (value === null || value === undefined) return "n/a";
  const cls = value >= 0 ? "up" : "down";
  const sign = value >= 0 ? "+" : "";
  return `<span class="${cls}">${sign}${Number(value).toFixed(2)}%</span>`;
};

const fmtNumber = (value) => {
  if (value === null || value === undefined) return "n/a";
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
  return Number(value).toLocaleString();
};

const escapeHtml = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));

async function fetchJson(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, { signal: controller.signal });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Scan failed");
    return payload;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("The scan took too long. Try turning News off, lowering Results, or scanning one section at a time.");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function tableRows(items, mode) {
  if (!items.length) {
    return `<div class="empty">No matches for the current filters.</div>`;
  }
  items.forEach((item, index) => signalsByKey.set(`${mode}:${index}:${item.symbol}`, item));
  const includePrediction = mode !== "movers";
  const rows = items.map((item, index) => {
    const planKey = `${mode}:${index}:${item.symbol}`;
    const grade = item.setup_grade || "C";
    const tags = (item.setup_tags || [])
      .map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`)
      .join("");
    const headlines = (item.headlines || [])
      .slice(0, 2)
      .map((headline) => `<a href="${escapeHtml(headline.link)}" target="_blank" rel="noreferrer">${escapeHtml(headline.title)}</a>`)
      .join("");
    return `
      <tr>
        <td><strong>${escapeHtml(item.symbol)}</strong><br>${escapeHtml(item.name)}</td>
        <td class="num">${fmtMoney(item.price)}</td>
        <td class="num">${fmtPct(item.change_pct)}</td>
        <td class="num">${fmtPct(item.trend_pct)}</td>
        <td class="num">${fmtMoney(item.volume_usd)}</td>
        <td class="num">${item.volume_ratio ? `${Number(item.volume_ratio).toFixed(2)}x` : "n/a"}</td>
        <td class="num">${fmtPct(item.volatility_pct)}</td>
        ${includePrediction ? `<td class="num"><span class="score">${item.prediction_score ?? "n/a"}</span></td>` : ""}
        <td class="pro-read"><span class="grade grade-${escapeHtml(grade).toLowerCase()}">${escapeHtml(grade)}</span>${tags || `<span class="tag muted-tag">needs confirmation</span>`}</td>
        <td class="notes">${escapeHtml((item.notes || []).join(", "))}</td>
        <td class="news">${headlines || "n/a"}</td>
        <td class="num"><button class="plan-btn" type="button" data-plan-key="${escapeHtml(planKey)}">Plan</button></td>
      </tr>
    `;
  }).join("");

  return `
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th class="num">Price</th>
          <th class="num">Today</th>
          <th class="num">Trend</th>
          <th class="num">Dollar Vol</th>
          <th class="num">Vol Ratio</th>
          <th class="num">Volatility</th>
          ${includePrediction ? `<th class="num">Score</th>` : ""}
          <th>Pro Read</th>
          <th>Signals</th>
          <th>News</th>
          <th class="num">Plan</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function yahooRows(items) {
  if (!items.length) {
    return `<div class="empty">No Yahoo gainers returned yet.</div>`;
  }
  const rows = items.map((item) => `
    <tr>
      <td><strong>${escapeHtml(item.symbol)}</strong><br>${escapeHtml(item.name)}</td>
      <td class="num">${fmtMoney(item.price)}</td>
      <td class="num">${fmtMoney(item.change)}</td>
      <td class="num">${fmtPct(item.change_pct)}</td>
      <td class="num">${fmtNumber(item.volume)}</td>
      <td class="num">${fmtNumber(item.avg_volume)}</td>
      <td class="num">${fmtMoney(item.market_cap)}</td>
      <td class="num">${item.pe_ratio ? Number(item.pe_ratio).toFixed(2) : "n/a"}</td>
      <td class="num">${fmtPct(item.fifty_two_week_change_pct)}</td>
      <td>${escapeHtml(item.fifty_two_week_range || "n/a")}</td>
    </tr>
  `).join("");

  return `
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th class="num">Price</th>
          <th class="num">Change</th>
          <th class="num">Change %</th>
          <th class="num">Volume</th>
          <th class="num">Avg Vol (3M)</th>
          <th class="num">Market Cap</th>
          <th class="num">P/E</th>
          <th class="num">52 Wk Change %</th>
          <th>52 Wk Range</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function asNumber(selector) {
  const value = Number(document.querySelector(selector).value);
  return Number.isFinite(value) ? value : 0;
}

function setPlanDefaults(item) {
  const entry = Number(item.price || 0);
  const volatility = Math.max(Number(item.volatility_pct || 0), 4);
  const stopPct = Math.min(Math.max(volatility * 0.75, 3), 18);
  const targetPct = Math.max(stopPct * 2.2, 8);

  document.querySelector("#entryPrice").value = entry ? entry.toFixed(entry < 1 ? 4 : 2) : "";
  document.querySelector("#stopPrice").value = entry ? (entry * (1 - stopPct / 100)).toFixed(entry < 1 ? 4 : 2) : "";
  document.querySelector("#targetPrice").value = entry ? (entry * (1 + targetPct / 100)).toFixed(entry < 1 ? 4 : 2) : "";
}

function selectSetup(item) {
  activeSetup = item;
  setPlanDefaults(item);
  activateTab("planPanel");
  updateSessionPlaybook();
  updatePlanLab();
}

function metric(label, value, tone = "") {
  return `<div class="metric ${tone}"><span>${label}</span><strong>${value}</strong></div>`;
}

function systemStep(label, value, tone = "") {
  return `<div class="system-step ${tone}"><span>${label}</span><strong>${value}</strong></div>`;
}

function updateEntryExitSystem(entry, stop, target, rr) {
  const systemEl = document.querySelector("#entryExitSystem");
  if (!systemEl) return;

  if (!activeSetup || !entry || !stop || !target || stop >= entry || target <= entry) {
    systemEl.innerHTML = systemStep("Status", "Choose Plan, then set entry, stop, and target.", "warn");
    return;
  }

  const grade = activeSetup.setup_grade || "C";
  const tags = activeSetup.setup_tags || [];
  const isHighQuality = ["A", "B"].includes(grade);
  const hasVolume = tags.some((tag) => tag.includes("volume"));
  const isThin = tags.some((tag) => tag.includes("thin liquidity"));
  const isWideRisk = tags.some((tag) => tag.includes("wide-risk"));
  const trimPrice = entry + (target - entry) * 0.55;
  const timeStop = activeSetup.market === "pre_market" ? "10-15 min without follow-through" : "5-8 min after entry";
  const trigger = activeSetup.market === "pre_market"
    ? "Enter only on pullback hold, pre-market high reclaim, or clean higher-low break."
    : "Enter only on opening range break, high-of-day reclaim, or volume-backed pullback hold.";
  const skipReasons = [];

  if (!isHighQuality) skipReasons.push("Pro Read is below B");
  if (rr < 2) skipReasons.push("reward/risk under 2:1");
  if (!hasVolume) skipReasons.push("no volume confirmation");
  if (isThin) skipReasons.push("thin liquidity");
  if (isWideRisk) skipReasons.push("range is too wide");

  systemEl.innerHTML = [
    systemStep("Enter", trigger, isHighQuality && hasVolume ? "good" : "warn"),
    systemStep("Hard stop", `Leave at ${fmtMoney(stop)}. No averaging down.`, "bad"),
    systemStep("First take-profit", `Trim some near ${fmtMoney(trimPrice)} or when move stalls.`, "good"),
    systemStep("Final exit", `Leave the rest at ${fmtMoney(target)} or if price loses entry.`, "good"),
    systemStep("Time stop", `Leave after ${timeStop}.`, "warn"),
    systemStep("Skip if", skipReasons.length ? skipReasons.join("; ") : "Setup passes the basic system checks.", skipReasons.length ? "bad" : "good"),
  ].join("");
}

function updatePlanLab() {
  const selectedEl = document.querySelector("#selectedSetup");
  const metricsEl = document.querySelector("#planMetrics");
  const disciplineEl = document.querySelector("#disciplineScore");
  if (!selectedEl || !metricsEl || !disciplineEl) return;

  if (!activeSetup) {
    metricsEl.innerHTML = metric("Status", "Waiting for setup");
    disciplineEl.textContent = "Checklist score: 0/5";
    updateEntryExitSystem(0, 0, 0, 0);
    return;
  }

  const entry = asNumber("#entryPrice");
  const stop = asNumber("#stopPrice");
  const target = asNumber("#targetPrice");
  const account = asNumber("#accountSize");
  const riskPct = asNumber("#riskPct");
  const riskBudget = account * (riskPct / 100);
  const riskPerShare = entry - stop;
  const rewardPerShare = target - entry;
  const rr = riskPerShare > 0 ? rewardPerShare / riskPerShare : 0;
  const shares = riskPerShare > 0 ? Math.floor(riskBudget / riskPerShare) : 0;
  const positionValue = shares * entry;
  const maxLoss = shares * riskPerShare;
  const targetProfit = shares * rewardPerShare;
  const checkedRules = [...document.querySelectorAll(".planRule")].filter((item) => item.checked).length;
  const setupTone = rr >= 2 && checkedRules >= 4 ? "good" : rr >= 1.5 && checkedRules >= 3 ? "warn" : "bad";

  selectedEl.innerHTML = `
    <div class="setup-symbol">${escapeHtml(activeSetup.symbol)}</div>
    <div class="setup-line">
      ${fmtMoney(activeSetup.price)} | ${fmtPct(activeSetup.change_pct)} today |
      Vol ${activeSetup.volume_ratio ? `${Number(activeSetup.volume_ratio).toFixed(2)}x` : "n/a"} |
      Score ${activeSetup.prediction_score ?? activeSetup.score ?? "n/a"}
    </div>
    <div class="setup-notes">${escapeHtml((activeSetup.notes || []).join(", ") || "No extra notes.")}</div>
  `;

  metricsEl.innerHTML = [
    metric("Risk budget", fmtMoney(riskBudget)),
    metric("Shares / units", shares > 0 ? shares.toLocaleString() : "Check stop", shares > 0 ? "" : "bad"),
    metric("Position value", fmtMoney(positionValue)),
    metric("Max loss", fmtMoney(maxLoss), "bad"),
    metric("Target profit", fmtMoney(targetProfit), targetProfit > 0 ? "good" : ""),
    metric("Reward/risk", rr > 0 ? `${rr.toFixed(2)}:1` : "Check prices", setupTone),
  ].join("");

  disciplineEl.textContent = `Checklist score: ${checkedRules}/5 | ${rr >= 2 ? "reward/risk is strong" : "tighten the plan before risking cash"}`;
  disciplineEl.className = `discipline-score ${setupTone}`;
  updateEntryExitSystem(entry, stop, target, rr);
}

function updateSessionPlaybook() {
  const metricsEl = document.querySelector("#sessionMetrics");
  const readinessEl = document.querySelector("#sessionReadiness");
  if (!metricsEl || !readinessEl) return;

  const account = asNumber("#accountSize");
  const riskPct = asNumber("#riskPct");
  const profitPct = asNumber("#sessionProfitPct");
  const stopPct = asNumber("#sessionStopPct");
  const maxTrades = asNumber("#maxTrades");
  const maxDailyLossPct = asNumber("#maxDailyLossPct");
  const dailyLossLimit = account * (maxDailyLossPct / 100);
  const perTradeRisk = account * (riskPct / 100);
  const targetPerWin = stopPct > 0 ? perTradeRisk * (profitPct / stopPct) : 0;
  const rr = stopPct > 0 ? profitPct / stopPct : 0;
  const lossTradesToStop = perTradeRisk > 0 ? Math.max(1, Math.floor(dailyLossLimit / perTradeRisk)) : 0;
  const readinessTone = rr >= 2 ? "good" : rr >= 1.5 ? "warn" : "bad";

  metricsEl.innerHTML = [
    metric("Target per win", fmtMoney(targetPerWin), targetPerWin > 0 ? "good" : ""),
    metric("Risk per trade", fmtMoney(perTradeRisk), "bad"),
    metric("Target/stop", rr > 0 ? `${rr.toFixed(2)}:1` : "Check settings", readinessTone),
    metric("Daily loss cap", fmtMoney(dailyLossLimit), "bad"),
    metric("Stop after losses", `${Math.min(lossTradesToStop, maxTrades || lossTradesToStop)} trade(s)`),
    metric("Max trades", maxTrades ? String(maxTrades) : "Set limit"),
  ].join("");
}
async function runScan() {
  const activePanel = document.querySelector(".tab-panel.active")?.id || "stocksPanel";
  if (activePanel === "yahooPanel") {
    await runYahooGainers();
    return;
  }
  if (activePanel === "premarketPanel") {
    await runPremarketScan();
    return;
  }
  if (activePanel === "cryptoPanel") {
    await runCryptoScan();
    return;
  }

  const params = new URLSearchParams({
    market: "stocks",
    min_price: document.querySelector("#minPrice").value,
    max_price: document.querySelector("#maxPrice").value,
    min_change: document.querySelector("#minChange").value,
    limit: document.querySelector("#limit").value,
    symbols: document.querySelector("#symbols").value,
    news: document.querySelector("#news").checked ? "true" : "false",
  });

  scanButton.disabled = true;
  statusEl.textContent = "Scanning stocks only...";
  try {
    const payload = await fetchJson(`/api/scan?${params.toString()}`);

    document.querySelector("#topMovers").innerHTML = tableRows(payload.top_movers, "movers");
    document.querySelector("#candidates").innerHTML = tableRows(payload.candidates, "candidates");
    statusEl.textContent = `Scanned ${payload.stock_universe_count ?? "configured"} stock symbols. ${payload.disclaimer}`;
  } catch (error) {
    statusEl.textContent = `Error: ${error.message}`;
  } finally {
    scanButton.disabled = false;
  }
}

async function runYahooGainers() {
  const params = new URLSearchParams({
    limit: document.querySelector("#limit").value,
  });

  scanButton.disabled = true;
  statusEl.textContent = "Loading Yahoo Finance top gainers...";
  try {
    const payload = await fetchJson(`/api/yahoo-gainers?${params.toString()}`);
    document.querySelector("#yahooGainers").innerHTML = yahooRows(payload.gainers || []);
    statusEl.textContent = `Loaded ${payload.count ?? 0} Yahoo top gainers. ${payload.disclaimer}`;
  } catch (error) {
    statusEl.textContent = `Error: ${error.message}`;
  } finally {
    scanButton.disabled = false;
  }
}

async function runPremarketScan() {
  const params = new URLSearchParams({
    min_price: document.querySelector("#minPrice").value,
    max_price: document.querySelector("#maxPrice").value,
    min_change: document.querySelector("#minChange").value || "5",
    min_volume_ratio: document.querySelector("#preVolumeRatio").value,
    limit: document.querySelector("#limit").value,
    symbols: document.querySelector("#symbols").value,
    news: document.querySelector("#news").checked ? "true" : "false",
  });

  premarketButton.disabled = true;
  statusEl.textContent = "Scanning extended-hours pre-market movers...";
  try {
    const payload = await fetchJson(`/api/premarket?${params.toString()}`);

    document.querySelector("#premarket").innerHTML = tableRows(payload.premarket, "premarket");
    statusEl.textContent = `Scanned ${payload.stock_universe_count ?? "configured"} stock symbols. ${payload.disclaimer}`;
  } catch (error) {
    statusEl.textContent = `Error: ${error.message}`;
  } finally {
    premarketButton.disabled = false;
  }
}

async function runCryptoScan() {
  const params = new URLSearchParams({
    min_price: document.querySelector("#minPrice").value,
    max_price: document.querySelector("#maxPrice").value,
    min_change: document.querySelector("#minChange").value,
    limit: document.querySelector("#limit").value,
  });

  cryptoButton.disabled = true;
  statusEl.textContent = "Scanning CoinGecko meme coin markets...";
  try {
    const payload = await fetchJson(`/api/crypto?${params.toString()}`);

    document.querySelector("#memeCoins").innerHTML = tableRows(payload.meme_coins, "crypto");
    statusEl.textContent = `Scanned CoinGecko meme category plus ${payload.crypto_universe_count ?? "configured"} configured coin IDs. ${payload.disclaimer}`;
  } catch (error) {
    statusEl.textContent = `Error: ${error.message}`;
  } finally {
    cryptoButton.disabled = false;
  }
}

function activateTab(id) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === id);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === id);
  });
  const market = document.querySelector("#market");
  if (market && id === "stocksPanel") market.value = "stocks";
  if (market && id === "cryptoPanel") market.value = "crypto";
  if (id === "yahooPanel") scanButton.textContent = "Load Yahoo Gainers";
  else if (id === "premarketPanel") scanButton.textContent = "Scan Pre-Market";
  else if (id === "cryptoPanel") scanButton.textContent = "Scan Crypto";
  else scanButton.textContent = "Scan Stocks";
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => activateTab(tab.dataset.tab));
});

document.addEventListener("click", (event) => {
  const planButton = event.target.closest(".plan-btn");
  if (!planButton) return;
  const item = signalsByKey.get(planButton.dataset.planKey);
  if (item) selectSetup(item);
});

["#accountSize", "#riskPct", "#entryPrice", "#stopPrice", "#targetPrice"].forEach((selector) => {
  document.querySelector(selector).addEventListener("input", updatePlanLab);
});

document.querySelectorAll(".planRule").forEach((input) => {
  input.addEventListener("change", updatePlanLab);
});

["#sessionProfitPct", "#sessionStopPct", "#maxTrades", "#maxDailyLossPct"].forEach((selector) => {
  const input = document.querySelector(selector);
  if (input) input.addEventListener("input", updateSessionPlaybook);
});

scanButton.addEventListener("click", runScan);
premarketButton.addEventListener("click", runPremarketScan);
cryptoButton.addEventListener("click", runCryptoScan);
scanButton.addEventListener("click", () => activateTab("stocksPanel"));
premarketButton.addEventListener("click", () => activateTab("premarketPanel"));
cryptoButton.addEventListener("click", () => activateTab("cryptoPanel"));
updatePlanLab();
updateSessionPlaybook();
