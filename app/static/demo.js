const $ = (selector) => document.querySelector(selector);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const previousSection = {
  document_id: "eba-model-risk",
  section_id: "12.3",
  title: "Model monitoring",
  text: "Institutions should review model monitoring controls annually.",
  page: 42,
  version: "2025",
};

const currentSection = {
  ...previousSection,
  text: "Institutions must review model monitoring controls annually.",
  version: "2026",
};

const impactCandidates = [
  {
    item_id: "control-mrm-07",
    name: "Model Monitoring Control MRM-07",
    item_type: "control",
    keywords: ["model", "monitoring", "controls", "annual"],
  },
  {
    item_id: "policy-model-risk",
    name: "Enterprise Model Risk Policy",
    item_type: "policy",
    keywords: ["model", "review", "risk"],
  },
  {
    item_id: "procedure-validation",
    name: "Annual Model Validation Procedure",
    item_type: "procedure",
    keywords: ["model", "annual", "review"],
  },
];

async function api(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${detail}`);
  }
  return response.json();
}

function activateStep(name) {
  document.querySelectorAll(".pipeline li").forEach((node) => node.classList.remove("running"));
  document.querySelector(`[data-step="${name}"]`).classList.add("running");
}

function completeStep(name) {
  const node = document.querySelector(`[data-step="${name}"]`);
  node.classList.remove("running");
  node.classList.add("done");
}

function setStatus(message) {
  $("#run-status").textContent = message;
}

function pct(value) {
  return `${Math.round(Number(value) * 100)}%`;
}

async function runAnalysis() {
  const button = $("#run-analysis");
  button.disabled = true;
  button.querySelector(".run-label").textContent = "Analysis running…";
  document.querySelectorAll(".pipeline li").forEach((node) => node.classList.remove("done", "running"));

  try {
    activateStep("ingest");
    setStatus("Stage 1/5 · sanitising and indexing the 2026 source");
    await api("/v1/documents", {
      source: "EBA Model Risk Guidelines 2026",
      title: "EBA Model Risk Guidelines",
      document_type: "guideline",
      jurisdiction: "EU",
      published_at: "2026-03-12",
      content: `# Model monitoring\n\nArticle 12.3\n\n${currentSection.text}`,
    });
    completeStep("ingest"); await sleep(240);

    activateStep("retrieve");
    setStatus("Stage 2/5 · retrieving grounded evidence");
    const search = await api("/v1/search", {query: "annual model monitoring controls", limit: 3});
    if (search.status !== "evidence_found" || !search.results.length) throw new Error("Evidence gate returned insufficient_evidence");
    const evidence = search.results[0];
    $("#citation-text").textContent = `“${evidence.text}”`;
    $("#citation-source").textContent = evidence.citation;
    $("#citation-score").textContent = `Relevance ${pct(evidence.score)}`;
    completeStep("retrieve"); await sleep(240);

    activateStep("compare");
    setStatus("Stage 3/5 · comparing structured regulatory sections");
    const changes = await api("/v1/changes/compare", {previous: [previousSection], current: [currentSection]});
    const change = changes[0];
    $("#materiality-score").textContent = pct(change.materiality_score);
    $("#confidence-score").textContent = pct(change.confidence_score);
    $("#signal-label").textContent = change.signals[0]?.replaceAll("_", " ") || "Material text modified";
    document.querySelector(".score-ring").style.background = `conic-gradient(var(--green) ${change.materiality_score * 360}deg, #e2e9e5 0)`;
    completeStep("compare"); await sleep(240);

    activateStep("review");
    setStatus("Stage 4/5 · verifying every claim against its citation");
    const review = await api("/v1/claims/review", change);
    const verified = review.accepted_claims.length > 0;
    $("#citation-state").textContent = verified ? "✓ VERIFIED" : "REVIEW REQUIRED";
    $("#citation-state").classList.toggle("success", verified);
    completeStep("review"); await sleep(240);

    activateStep("impact");
    setStatus("Stage 5/5 · mapping regulatory concepts to internal artefacts");
    const impacts = await api("/v1/impacts/analyze", {change, candidates: impactCandidates});
    $("#impact-list").innerHTML = impacts.length
      ? impacts.map((impact) => `<li><span>${impact.candidate.name}</span><small>${impact.candidate.item_type} · human validation required</small><b>${pct(impact.relevance_score)}</b></li>`).join("")
      : '<li class="placeholder">No configured artefact exceeded the relevance threshold.</li>';
    completeStep("impact");
    setStatus(`Complete · ${review.accepted_claims.length} grounded claim(s) · ${impacts.length} potential impact(s)`);
    $("#results").classList.add("revealed");
  } catch (error) {
    setStatus(`Analysis stopped safely · ${error.message}`);
  } finally {
    button.disabled = false;
    button.querySelector(".run-label").textContent = "Run analysis again";
  }
}

function findMetric(report, key) {
  const summary = report.summary || report.metrics || report;
  const aliases = {
    recall_at_k: [summary.retrieval?.recall_at_k, summary.recall_at_k, summary["recall@k"]],
    mrr: [summary.retrieval?.mean_reciprocal_rank, summary.retrieval?.mrr, summary.mrr],
  };
  return aliases[key].find((value) => typeof value === "number");
}

function confidenceInterval(report, metric) {
  return report.summary?.retrieval?.confidence_intervals?.[metric];
}

function describeBenchmark(report, source) {
  const metadata = report.benchmark || {};
  const summary = report.summary || {};
  const parts = ["Synthetic evaluation report"];
  if (metadata.version) parts.push(`v${metadata.version}`);
  if (metadata.split) parts.push(`${metadata.split} split`);
  const queries = summary.retrieval?.evaluated_cases;
  const changes = report.details?.changes?.length;
  if (Number.isInteger(queries)) parts.push(`${queries} queries`);
  if (Number.isInteger(changes)) parts.push(`${changes} changes`);
  return parts.length > 1 ? parts.join(" · ") : `Measured benchmark · ${source}`;
}

async function loadMetrics() {
  try {
    const response = await fetch("/demo/metrics");
    const report = await response.json();
    if (!report.available) {
      $("#metrics-source").textContent = "Run the benchmark to populate measured results.";
      return;
    }
    $("#metrics-source").textContent = describeBenchmark(report.metrics, report.source);
    ["recall_at_k", "mrr"].forEach((key) => {
      const value = findMetric(report.metrics, key);
      if (value === undefined) return;
      document.querySelector(`[data-metric="${key}"]`).textContent = pct(value);
      document.querySelector(`[data-bar="${key}"]`).style.width = pct(value);
    });
    const recallInterval = confidenceInterval(report.metrics, "recall_at_k");
    const queryCount = report.metrics.summary?.retrieval?.evaluated_cases;
    if (recallInterval) {
      document.querySelector('[data-detail="recall_at_k"]').textContent =
        `95% CI ${pct(recallInterval.lower)}–${pct(recallInterval.upper)} · n=${queryCount}`;
    }
    if (Number.isInteger(queryCount)) {
      document.querySelector('[data-metric="queries"]').textContent = `n=${queryCount}`;
      document.querySelector('[data-bar="queries"]').style.width = "100%";
    }
    const changes = report.metrics.details?.changes || [];
    const passedChanges = changes.filter(
      (row) => row.expected_material === row.predicted_material,
    ).length;
    if (changes.length) {
      document.querySelector('[data-metric="change_checks"]').textContent =
        `${passedChanges}/${changes.length}`;
      document.querySelector('[data-bar="change_checks"]').style.width =
        pct(passedChanges / changes.length);
    }
  } catch (_) {
    $("#metrics-source").textContent = "Benchmark report unavailable.";
  }
}

$("#run-analysis").addEventListener("click", runAnalysis);
loadMetrics();

if (new URLSearchParams(window.location.search).get("autorun") === "1") {
  window.setTimeout(runAnalysis, 250);
}
