const form = document.querySelector("#forecast-form");
const submitButton = document.querySelector("#submit-button");
const errorBox = document.querySelector("#error-box");
const warningBox = document.querySelector("#warning-box");
const dashboard = document.querySelector("#dashboard");
const emptyState = document.querySelector("#empty-state");
const resultTitle = document.querySelector("#result-title");

const citySelect = document.querySelector("#city-select");
const regionSelect = document.querySelector("#region-select");
const neighbourhoodSelect = document.querySelector("#neighbourhood-select");
const marketTypeSelect = document.querySelector("#market-type-select");
const propertyTypeSelect = document.querySelector("#property-type-select");
const roomTypeSelect = document.querySelector("#room-type-select");
const financingSelect = document.querySelector("#financing-select");

const numericFields = new Set([
  "accommodates",
  "bedrooms",
  "beds",
  "bathrooms",
  "minimum_nights",
  "maximum_nights",
  "property_acquisition_cost",
  "furnishing_setup_cost",
]);

const booleanFields = new Set([
  "instant_bookable",
  "has_wifi",
  "has_aircon",
  "has_pool",
  "has_parking",
  "has_washer",
  "has_dryer",
  "has_kitchen",
  "has_tv",
  "has_heating",
]);

let optionsPayload = null;

function currency(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return new Intl.NumberFormat("en-IE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function percent(value, decimals = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${(Number(value) * 100).toFixed(decimals)}%`;
}

function number(value, decimals = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(decimals);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setText(id, value) {
  document.querySelector(`#${id}`).textContent = value;
}

function titleLabel(value) {
  return String(value)
    .replaceAll("_", " ")
    .split(" ")
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : part))
    .join(" ");
}

function formatMarketType(value) {
  return titleLabel(value);
}

function formatScenarioLabel(value) {
  const map = {
    cash_purchase: "Cash purchase",
    loan_50: "50% bank loan",
    loan_70: "70% bank loan",
    loan_80: "80% bank loan",
    loan_90: "90% bank loan",
  };
  return map[value] || titleLabel(value);
}

function getOptionValue(option) {
  return typeof option === "string" ? option : option.value;
}

function getOptionLabel(option, formatter = titleLabel) {
  if (typeof option === "string") {
    return formatter(option);
  }
  return option.label || formatter(option.value);
}

function populateSelect(select, options, selectedValue, formatter = titleLabel) {
  select.innerHTML = options
    .map((option) => {
      const value = getOptionValue(option);
      const label = getOptionLabel(option, formatter);
      const selected = value === selectedValue ? " selected" : "";
      return `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(label)}</option>`;
    })
    .join("");
}

function defaultChoice(options, preferredValue) {
  if (preferredValue && options.includes(preferredValue)) {
    return preferredValue;
  }
  return options[0];
}

function renderMessageBox(container, messages) {
  const messageList = Array.isArray(messages) ? messages : [messages];
  if (!messageList.length) {
    container.hidden = true;
    container.innerHTML = "";
    return;
  }

  container.hidden = false;
  if (messageList.length === 1) {
    container.innerHTML = `<p>${escapeHtml(messageList[0])}</p>`;
    return;
  }
  container.innerHTML = `<ul>${messageList.map((message) => `<li>${escapeHtml(message)}</li>`).join("")}</ul>`;
}

function showError(messages) {
  renderMessageBox(errorBox, messages);
}

function clearError() {
  errorBox.hidden = true;
  errorBox.innerHTML = "";
}

function showWarnings(messages) {
  renderMessageBox(warningBox, messages);
}

function clearWarnings() {
  warningBox.hidden = true;
  warningBox.innerHTML = "";
}

function parseApiError(errorPayload) {
  if (!errorPayload) {
    return ["Something went wrong while generating the forecast."];
  }

  const { detail } = errorPayload;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (item && typeof item === "object") {
        const location = Array.isArray(item.loc)
          ? item.loc.filter((part) => part !== "body").join(" > ")
          : "";
        const message = item.msg || JSON.stringify(item);
        return location ? `${location}: ${message}` : message;
      }
      return String(item);
    });
  }

  if (typeof detail === "string") {
    return [detail];
  }

  if (detail && typeof detail === "object") {
    return [JSON.stringify(detail)];
  }

  return ["Something went wrong while generating the forecast."];
}

function renderFactRows(containerId, rows) {
  const container = document.querySelector(`#${containerId}`);
  container.innerHTML = rows
    .map(
      (row) => `
        <div class="fact-row">
          <span>${escapeHtml(row.label)}</span>
          <strong class="${escapeHtml(row.valueClass || "")}">${escapeHtml(row.value)}</strong>
        </div>
      `
    )
    .join("");
}

function renderConfidenceCards(result) {
  const confidence = result.confidence;
  const container = document.querySelector("#confidence-grid");
  const cards = [
    {
      title: "Likely price range",
      range: result.statistical_evidence.price_confidence_interval_68,
      formatter: currency,
    },
    {
      title: "Likely occupancy range",
      range: result.statistical_evidence.occupancy_confidence_interval_68,
      formatter: (value) => percent(value),
    },
    {
      title: "Likely monthly net",
      range: confidence.monthly_net_range_68,
      formatter: currency,
    },
    {
      title: "Likely annual net",
      range: confidence.annual_net_range_68,
      formatter: currency,
    },
    {
      title: "Wider stress-test range (price)",
      range: result.statistical_evidence.price_confidence_interval_95,
      formatter: currency,
    },
    {
      title: "Wider stress-test range (occupancy)",
      range: result.statistical_evidence.occupancy_confidence_interval_95,
      formatter: (value) => percent(value),
    },
    {
      title: "Wider stress-test monthly net",
      range: confidence.monthly_net_range_95,
      formatter: currency,
    },
    {
      title: "Wider stress-test annual net",
      range: confidence.annual_net_range_95,
      formatter: currency,
    },
  ];

  container.innerHTML = cards
    .map(
      (card) => `
        <div class="confidence-card">
          <span>${escapeHtml(card.title)}</span>
          <div class="confidence-values">
            <div><small>Low</small><strong>${escapeHtml(card.formatter(card.range.low))}</strong></div>
            <div><small>Base</small><strong>${escapeHtml(card.formatter(card.range.base))}</strong></div>
            <div><small>High</small><strong>${escapeHtml(card.formatter(card.range.high))}</strong></div>
          </div>
        </div>
      `
    )
    .join("");
}

function renderCostBreakdown(costBreakdown) {
  const container = document.querySelector("#cost-breakdown-groups");
  const groups = [
    {
      title: "Booking and guest costs",
      rows: [
        { label: "Platform fees", value: currency(costBreakdown.platform_fees) },
        { label: "Cleaning", value: currency(costBreakdown.cleaning_cost) },
        { label: "Laundry", value: currency(costBreakdown.laundry_cost) },
        { label: "Toiletries", value: currency(costBreakdown.toiletries_cost) },
      ],
    },
    {
      title: "Property running costs",
      rows: [
        { label: "Base utilities", value: currency(costBreakdown.base_utility_cost) },
        { label: "Variable utilities", value: currency(costBreakdown.variable_utility_cost) },
        { label: "Insurance", value: currency(costBreakdown.insurance_cost) },
        { label: "Condo", value: currency(costBreakdown.condo_cost) },
        { label: "Other fixed costs", value: currency(costBreakdown.other_fixed_cost) },
        { label: "Maintenance reserve", value: currency(costBreakdown.maintenance_reserve) },
      ],
    },
    {
      title: "Mandatory company/property costs",
      rows: [
        { label: "Accounting", value: currency(costBreakdown.annual_accounting_cost) },
        { label: "Licensing", value: currency(costBreakdown.annual_licensing_cost) },
        { label: "IMI/property tax", value: currency(costBreakdown.annual_imi_cost) },
      ],
    },
    {
      title: "Financing and tax",
      rows: [
        { label: "Debt service", value: currency(costBreakdown.debt_service) },
        { label: "Interest cost", value: currency(costBreakdown.annual_interest_cost) },
        { label: "Principal repayment", value: currency(costBreakdown.annual_principal_repayment) },
        { label: "Income tax", value: currency(costBreakdown.tax_due) },
      ],
    },
  ];

  container.innerHTML = groups
    .map(
      (group) => `
        <div class="cost-group">
          <h4>${escapeHtml(group.title)}</h4>
          ${group.rows
            .map(
              (row) => `
                <div class="fact-row">
                  <span>${escapeHtml(row.label)}</span>
                  <strong>${escapeHtml(row.value)}</strong>
                </div>
              `
            )
            .join("")}
        </div>
      `
    )
    .join("");
}

function renderScenarioComparison(rows) {
  const body = document.querySelector("#scenario-comparison-body");
  body.innerHTML = rows
    .map(
      (row) => `
        <tr class="${row.is_selected ? "selected-scenario" : ""}">
          <td class="scenario-name">${escapeHtml(row.scenario_label || formatScenarioLabel(row.financing_scenario))}</td>
          <td>${escapeHtml(currency(row.monthly_net_income_after_tax))}</td>
          <td>${escapeHtml(currency(row.annual_net_income_after_tax))}</td>
          <td>${escapeHtml(currency(row.estimated_equity_required))}</td>
          <td>${escapeHtml(currency(row.estimated_loan_amount))}</td>
          <td>${escapeHtml(currency(row.monthly_debt_service))}</td>
          <td>${escapeHtml(percent(row.cash_on_equity_return))}</td>
          <td>${escapeHtml(row.payback_years === null ? "Not positive yet" : `${number(row.payback_years, 2)} years`)}</td>
        </tr>
      `
    )
    .join("");
}

function renderPricingGuidance(guidance) {
  renderFactRows("pricing-guidance-grid", [
    { label: "Current predicted occupancy", value: percent(guidance.current_occupancy) },
    { label: "Stabilized market target", value: percent(guidance.market_target_occupancy) },
    { label: "Recommendation", value: guidance.recommendation, valueClass: "long-value" },
  ]);
  document.querySelector("#pricing-guidance-note").textContent = guidance.note;
}

function yearLabel(value) {
  const labels = {
    1: "Year 1: Launch year",
    2: "Year 2: Building trust",
    3: "Year 3: Stabilized scenario",
  };
  return labels[value] || `Year ${value}`;
}

function renderThreeYearScenario(payload) {
  const body = document.querySelector("#three-year-scenario-body");
  body.innerHTML = (payload.years || [])
    .map(
      (row) => `
        <tr>
          <td class="scenario-name">${escapeHtml(yearLabel(row.year))}</td>
          <td>${escapeHtml(percent(row.occupancy_rate))}</td>
          <td>${escapeHtml(number(row.occupied_nights, 1))}</td>
          <td>${escapeHtml(number(row.expected_reviews, 1))}</td>
          <td>${escapeHtml(currency(row.monthly_net_income_after_tax))}</td>
          <td>${escapeHtml(currency(row.annual_net_income_after_tax))}</td>
          <td class="long-value">${escapeHtml(row.scenario_note)}</td>
        </tr>
      `
    )
    .join("");

  document.querySelector("#three-year-method").textContent =
    `${payload.method} Stabilized target: ${percent(payload.market_stabilized_target)}.`;
  document.querySelector("#three-year-note").textContent = payload.important_note;
}

function renderForecast(result) {
  const predictions = result.predictions;
  const financials = result.financials;
  const statistics = result.statistical_evidence;
  const modelInfo = result.model_info;
  const assumptionsDetail = result.assumptions_detail;
  const taxBreakdown = result.tax_breakdown;

  clearWarnings();
  if (result.warnings && result.warnings.length) {
    showWarnings(result.warnings);
  }

  emptyState.hidden = true;
  dashboard.hidden = false;
  resultTitle.textContent = "Forecast dashboard";

  setText("diagnosis-headline", result.diagnosis.headline);
  setText("diagnosis-note", result.diagnosis.financing_note);
  setText("nightly-price", currency(predictions.nightly_price));
  setText("occupancy-rate", percent(predictions.occupancy_rate));
  setText("occupied-nights", `${number(predictions.occupied_nights, 1)} occupied nights, ${number(predictions.expected_reviews_first_year, 1)} estimated reviews`);
  setText("monthly-net", currency(financials.monthly_net_income_after_tax));
  setText("annual-net", currency(financials.annual_net_income_after_tax));
  setText("review-forecast", `${number(predictions.expected_reviews_per_month, 2)} expected reviews per month`);

  setText("monthly-gross", currency(financials.monthly_gross_revenue));
  setText("monthly-operating", currency(financials.monthly_operating_cost));
  setText("monthly-noi", currency(financials.monthly_noi));
  setText("monthly-bank", currency(financials.monthly_debt_service));
  setText("monthly-tax", currency(financials.monthly_tax_due));
  setText("monthly-final-net", currency(financials.monthly_net_income_after_tax));

  setText("capex", currency(financials.estimated_total_project_capex));
  setText("equity", currency(financials.estimated_equity_required));
  setText("loan", currency(financials.estimated_loan_amount));
  setText("cash-return", percent(financials.cash_on_equity_return));
  setText("payback", financials.payback_years === null ? "Not positive yet" : `${number(financials.payback_years, 2)} years`);

  renderFactRows("model-info-grid", [
    { label: "Price model file", value: modelInfo.price_model_file || "-", valueClass: "model-value long-value" },
    { label: "Occupancy model file", value: modelInfo.occupancy_model_file || "-", valueClass: "model-value long-value" },
    { label: "Selected price model", value: modelInfo.selected_price_model || "-", valueClass: "long-value" },
    { label: "Selected occupancy model", value: modelInfo.selected_occupancy_model || "-", valueClass: "long-value" },
    { label: "Forecast strength", value: statistics.evidence_rating || "-" },
    { label: "Price R2 / RMSE / MAE", value: `${number(statistics.price_model_r2, 4)} / ${number(statistics.price_model_rmse, 2)} / ${number(statistics.price_model_mae, 2)}` },
    { label: "Occupancy R2 / RMSE / MAE", value: `${number(statistics.occupancy_model_r2, 4)} / ${number(statistics.occupancy_model_rmse, 4)} / ${number(statistics.occupancy_model_mae, 4)}` },
  ]);
  document.querySelector("#model-info-note").textContent = statistics.interpretation_note;

  renderFactRows("assumptions-grid", [
    { label: "Effective tax rate", value: percent(assumptionsDetail.effective_tax_rate, 1) },
    { label: "Loan term", value: `${number(assumptionsDetail.loan_term_years, 0)} years` },
    { label: "Interest rate", value: percent(assumptionsDetail.annual_interest_rate, 2) },
    { label: "IMI rate", value: percent(assumptionsDetail.imi_rate_pct, 2) },
    { label: "Closing cost rate", value: percent(assumptionsDetail.closing_cost_pct, 1) },
    { label: "Platform fee", value: percent(assumptionsDetail.platform_fee_pct, 1) },
    { label: "Management fee", value: percent(assumptionsDetail.management_fee_pct, 1) },
    { label: "Review capture rate", value: percent(assumptionsDetail.review_capture_rate, 1) },
  ]);

  renderConfidenceCards(result);
  document.querySelector("#confidence-note").textContent = statistics.confidence_level_used;

  renderCostBreakdown(result.cost_breakdown);

  renderFactRows("tax-breakdown-grid", [
    { label: "Taxable income", value: currency(taxBreakdown.taxable_income) },
    { label: "Interest deduction", value: currency(taxBreakdown.interest_deduction) },
    { label: "Effective tax rate", value: percent(taxBreakdown.effective_tax_rate, 1) },
    { label: "Annual tax due", value: currency(taxBreakdown.annual_tax_due) },
  ]);
  document.querySelector("#tax-note").textContent = taxBreakdown.tax_note;
  document.querySelector("#tax-disclaimer").textContent = taxBreakdown.disclaimer;

  renderScenarioComparison(result.scenario_comparison || []);
  renderPricingGuidance(result.pricing_guidance);
  renderThreeYearScenario(result.three_year_scenario);
}

function collectPayload() {
  const data = new FormData(form);
  const payload = {};

  for (const [key, value] of data.entries()) {
    if (numericFields.has(key)) {
      payload[key] = Number(value);
    } else {
      payload[key] = value;
    }
  }

  for (const key of booleanFields) {
    payload[key] = Boolean(data.get(key));
  }

  return payload;
}

function populateStaticSelects() {
  populateSelect(propertyTypeSelect, optionsPayload.property_types, "Entire rental unit", (value) => value);
  populateSelect(roomTypeSelect, optionsPayload.room_types, "Entire home/apt", (value) => value);
  populateSelect(financingSelect, optionsPayload.financing_scenarios, "loan_80", formatScenarioLabel);
}

function updateRegionAndDependents(preferredRegion = null, preferredNeighbourhood = null, preferredMarketType = null) {
  const cityKey = citySelect.value;
  const cityConfig = optionsPayload.locations[cityKey];
  const regionKeys = Object.keys(cityConfig.regions);
  const regionValue = defaultChoice(regionKeys, preferredRegion);
  populateSelect(regionSelect, regionKeys, regionValue, titleLabel);

  const regionConfig = cityConfig.regions[regionValue];
  const neighbourhoodValue = defaultChoice(regionConfig.neighbourhoods, preferredNeighbourhood);
  populateSelect(neighbourhoodSelect, regionConfig.neighbourhoods, neighbourhoodValue, titleLabel);

  const marketTypeValue = defaultChoice(regionConfig.market_types, preferredMarketType);
  populateSelect(marketTypeSelect, regionConfig.market_types, marketTypeValue, formatMarketType);
}

function updateCityOptions() {
  const cityKeys = Object.keys(optionsPayload.locations);
  const selectedCity = defaultChoice(cityKeys, "lisbon");
  populateSelect(citySelect, cityKeys, selectedCity, titleLabel);
  updateRegionAndDependents("lisbon_inland", "baixa", "urban");
}

async function loadOptions() {
  const response = await fetch("/api/options");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(parseApiError(payload).join(" "));
  }

  optionsPayload = payload;
  populateStaticSelects();
  updateCityOptions();
}

citySelect.addEventListener("change", () => {
  updateRegionAndDependents();
});

regionSelect.addEventListener("change", () => {
  updateRegionAndDependents(regionSelect.value);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  clearWarnings();
  submitButton.disabled = true;
  submitButton.textContent = "Forecasting...";

  try {
    const response = await fetch("/api/predict", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(collectPayload()),
    });

    const payload = await response.json();
    if (!response.ok) {
      showError(parseApiError(payload));
      return;
    }

    renderForecast(payload);
  } catch (error) {
    showError([`The local app could not complete the request. ${String(error)}`]);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Generate forecast";
  }
});

window.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadOptions();
  } catch (error) {
    showError([`The dashboard could not load its option lists. ${String(error)}`]);
  }
});
