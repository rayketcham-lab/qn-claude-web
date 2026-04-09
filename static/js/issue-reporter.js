/**
 * issue-reporter.js — Embeddable GitHub issue reporter widget
 *
 * Drop a single <script> tag on any page to add a floating feedback button
 * that creates structured GitHub issues via a multi-step wizard.
 *
 * No dependencies. No framework. No build step.
 *
 * Mode 1 — Direct to GitHub (no backend needed):
 *   IssueReporter.init({
 *     github: { repo: "owner/repo", token: "github_pat_xxxx" },
 *     projectName: "My App"
 *   });
 *
 * Mode 1b — GitHub Enterprise Server (on-prem):
 *   IssueReporter.init({
 *     github: {
 *       repo: "org/repo",
 *       token: "github_pat_xxxx",
 *       apiUrl: "https://your-ghes-host/api/v3"
 *     },
 *     projectName: "My App"
 *   });
 *
 * Mode 2 — Via your backend (one route):
 *   IssueReporter.init({
 *     endpoint: "/api/report",
 *     projectName: "My App"
 *   });
 *
 * @license Apache-2.0
 * @see https://github.com/rayketcham-lab/issue-reporter
 */
(function () {
  "use strict";

  var VERSION = "2.2.0";
  var REPO_URL = "https://github.com/rayketcham-lab/issue-reporter";

  // Guard against double-init
  if (window.IssueReporter && window.IssueReporter._initialized) {
    return;
  }

  // -------------------------------------------------------------------------
  // Default configuration
  // -------------------------------------------------------------------------

  var DEFAULT_ISSUE_TYPES = [
    { id: "bug",             label: "Bug Report",       icon: "\uD83D\uDC1B", description: "Something is broken",           color: "red",    showExpected: true },
    { id: "data_issue",      label: "Data Issue",       icon: "\uD83D\uDDC3\uFE0F", description: "Wrong or missing data",         color: "amber",  showExpected: true },
    { id: "ui_bug",          label: "UI / Display Bug", icon: "\uD83D\uDDA5\uFE0F", description: "Visual or layout problem",      color: "blue",   showExpected: true },
    { id: "broken_link",     label: "Broken Link",      icon: "\uD83D\uDD17", description: "Link or page not working",      color: "orange", showExpected: true },
    { id: "feature_request", label: "Feature Request",  icon: "\uD83D\uDCA1", description: "Want something new",            color: "green",  showExpected: false },
    { id: "performance",     label: "Performance",      icon: "\u26A1",       description: "Slow or unresponsive",          color: "purple", showExpected: false },
    { id: "other",           label: "Other",            icon: "\uD83D\uDCAC", description: "Something else",                color: "gray",   showExpected: false },
  ];

  var DEFAULTS = {
    endpoint: "",
    github: null,
    projectName: "",
    position: "bottom-right",
    buttonText: "Report Issue",
    issueTypes: DEFAULT_ISSUE_TYPES,
    token: "",
  };

  // Map issue types to conventional-commit prefixes
  var PREFIX_MAP = {
    bug: "fix",
    feature_request: "feat",
    data_issue: "data",
    ui_bug: "fix",
    broken_link: "fix",
    performance: "perf",
    other: "issue",
  };

  // Map issue types to GitHub labels
  var LABEL_MAP = {
    bug: ["bug"],
    feature_request: ["enhancement"],
    data_issue: ["bug", "data"],
    ui_bug: ["bug", "ui"],
    broken_link: ["bug"],
    performance: ["performance"],
    other: [],
  };

  // Type-specific prompts for the Details step
  var CONTEXT_PROMPTS = {
    bug:             { heading: "What's broken?",            sectionLabel: "Where on the page?",           descLabel: "Describe the bug" },
    data_issue:      { heading: "What data is wrong?",       sectionLabel: "Which section has bad data?",  descLabel: "What's incorrect and what should it be?" },
    ui_bug:          { heading: "What looks wrong?",         sectionLabel: "Which part of the page?",      descLabel: "Describe the visual problem" },
    broken_link:     { heading: "What's broken?",            sectionLabel: "Where on the page?",           descLabel: "What did you click and what happened?" },
    feature_request: { heading: "What would you like?",      sectionLabel: "Which area of the app?",       descLabel: "Describe the feature you want" },
    performance:     { heading: "What's slow?",              sectionLabel: "Which part of the page?",      descLabel: "Describe the performance problem" },
    other:           { heading: "Tell us more",              sectionLabel: "Where is the issue?",          descLabel: "Describe the issue in detail" },
  };

  // Severity options
  var SEVERITY_OPTIONS = [
    { id: "low",      label: "Low",      desc: "Minor annoyance" },
    { id: "medium",   label: "Medium",   desc: "Impacts usability" },
    { id: "high",     label: "High",     desc: "Major functionality broken" },
    { id: "critical", label: "Critical", desc: "Data loss or security" },
  ];

  // Color definitions for type cards (dark theme)
  var TYPE_COLORS = {
    red:    { border: "rgba(239,68,68,0.3)",   borderHover: "rgba(239,68,68,0.6)",   bg: "rgba(239,68,68,0.05)",   bgHover: "rgba(239,68,68,0.1)",   bgSelected: "rgba(239,68,68,0.2)",   borderSelected: "rgba(239,68,68,1)",   ring: "rgba(239,68,68,0.4)",   icon: "#f87171" },
    amber:  { border: "rgba(245,158,11,0.3)",  borderHover: "rgba(245,158,11,0.6)",  bg: "rgba(245,158,11,0.05)",  bgHover: "rgba(245,158,11,0.1)",  bgSelected: "rgba(245,158,11,0.2)",  borderSelected: "rgba(245,158,11,1)",  ring: "rgba(245,158,11,0.4)",  icon: "#fbbf24" },
    orange: { border: "rgba(249,115,22,0.3)",  borderHover: "rgba(249,115,22,0.6)",  bg: "rgba(249,115,22,0.05)",  bgHover: "rgba(249,115,22,0.1)",  bgSelected: "rgba(249,115,22,0.2)",  borderSelected: "rgba(249,115,22,1)",  ring: "rgba(249,115,22,0.4)",  icon: "#fb923c" },
    purple: { border: "rgba(168,85,247,0.3)",  borderHover: "rgba(168,85,247,0.6)",  bg: "rgba(168,85,247,0.05)",  bgHover: "rgba(168,85,247,0.1)",  bgSelected: "rgba(168,85,247,0.2)",  borderSelected: "rgba(168,85,247,1)",  ring: "rgba(168,85,247,0.4)",  icon: "#c084fc" },
    blue:   { border: "rgba(59,130,246,0.3)",  borderHover: "rgba(59,130,246,0.6)",  bg: "rgba(59,130,246,0.05)",  bgHover: "rgba(59,130,246,0.1)",  bgSelected: "rgba(59,130,246,0.2)",  borderSelected: "rgba(59,130,246,1)",  ring: "rgba(59,130,246,0.4)",  icon: "#60a5fa" },
    green:  { border: "rgba(34,197,94,0.3)",   borderHover: "rgba(34,197,94,0.6)",   bg: "rgba(34,197,94,0.05)",   bgHover: "rgba(34,197,94,0.1)",   bgSelected: "rgba(34,197,94,0.2)",   borderSelected: "rgba(34,197,94,1)",   ring: "rgba(34,197,94,0.4)",   icon: "#4ade80" },
    gray:   { border: "rgba(107,114,128,0.3)", borderHover: "rgba(107,114,128,0.6)", bg: "rgba(107,114,128,0.05)", bgHover: "rgba(107,114,128,0.1)", bgSelected: "rgba(107,114,128,0.2)", borderSelected: "rgba(107,114,128,1)", ring: "rgba(107,114,128,0.4)", icon: "#9ca3af" },
  };

  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------

  var config = {};
  var modalEl = null;
  var backdropEl = null;
  var buttonEl = null;
  var inspectBannerEl = null;

  // Wizard state
  var state = {
    step: 0,            // 0=type, 1=details, 2=review
    selectedType: null,
    description: "",
    section: "",
    elementInfo: null,
    expectedBehavior: "",
    severity: "medium",
    sections: [],
    pageTitle: "",
    pageType: "",
    submitting: false,
    result: null,       // { success, url, error }
  };

  // Inspect mode state
  var inspectActive = false;
  var inspectHandlers = {};

  // Console/fetch capture
  var consoleErrors = [];
  var apiCalls = [];
  var origConsoleError = null;
  var origConsoleWarn = null;
  var origFetch = null;

  // -------------------------------------------------------------------------
  // SVG icons (hardcoded constants, safe — no user input)
  // -------------------------------------------------------------------------

  var BUG_ICON_SVG = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">' +
    '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 ' +
    '15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>';

  var CROSSHAIR_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">' +
    '<circle cx="12" cy="12" r="10"/><line x1="22" y1="12" x2="18" y2="12"/>' +
    '<line x1="6" y1="12" x2="2" y2="12"/><line x1="12" y1="6" x2="12" y2="2"/>' +
    '<line x1="12" y1="22" x2="12" y2="18"/></svg>';

  // -------------------------------------------------------------------------
  // CSS — scoped under .ir- prefix, dark theme throughout
  // -------------------------------------------------------------------------

  var CSS = [
    // Font stack
    ".ir-widget,.ir-widget *,.ir-widget *::before,.ir-widget *::after{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;}",

    // Floating trigger button
    ".ir-btn{",
      "position:fixed;z-index:2147483646;",
      "display:flex;align-items:center;gap:8px;",
      "padding:12px 20px;border:none;border-radius:12px;",
      "background:#2563eb;color:#fff;font-weight:600;font-size:14px;line-height:1;",
      "cursor:pointer;box-shadow:0 4px 20px rgba(37,99,235,0.35);",
      "transition:all 0.2s ease;",
    "}",
    ".ir-btn:hover{background:#3b82f6;transform:translateY(-2px);box-shadow:0 6px 24px rgba(37,99,235,0.45);}",
    ".ir-btn:active{transform:translateY(0);}",
    ".ir-btn svg{width:16px;height:16px;fill:currentColor;flex-shrink:0;}",
    ".ir-btn--br{bottom:24px;right:24px;}",
    ".ir-btn--bl{bottom:24px;left:24px;}",

    // Backdrop
    ".ir-backdrop{",
      "position:fixed;inset:0;z-index:2147483647;",
      "background:rgba(0,0,0,0.6);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);",
      "display:flex;align-items:center;justify-content:center;",
      "opacity:0;transition:opacity 0.25s ease;",
    "}",
    ".ir-backdrop--visible{opacity:1;}",

    // Modal
    ".ir-modal{",
      "background:#111827;border:1px solid #374151;border-radius:16px;",
      "box-shadow:0 25px 80px rgba(0,0,0,0.5);",
      "width:94%;max-width:680px;max-height:90vh;",
      "display:flex;flex-direction:column;",
      "font-size:14px;line-height:1.5;color:#e5e7eb;",
      "transform:translateY(16px);transition:transform 0.25s ease;",
      "overflow:hidden;",
    "}",
    ".ir-backdrop--visible .ir-modal{transform:translateY(0);}",

    // Content area — flex column so body scrolls and footer stays pinned
    "#ir-content{display:flex;flex-direction:column;flex:1 1 auto;min-height:0;overflow:hidden;}",

    // Header
    ".ir-header{",
      "display:flex;align-items:center;justify-content:space-between;",
      "padding:16px 20px;border-bottom:1px solid #1f2937;flex-shrink:0;",
    "}",
    ".ir-header-left{display:flex;align-items:center;gap:10px;}",
    ".ir-header-icon{color:#60a5fa;font-size:18px;}",
    ".ir-header h2{margin:0;font-size:16px;font-weight:600;color:#f3f4f6;}",
    ".ir-close{",
      "background:none;border:none;cursor:pointer;padding:6px;",
      "color:#6b7280;font-size:18px;line-height:1;border-radius:8px;",
      "transition:background 0.15s,color 0.15s;",
    "}",
    ".ir-close:hover{color:#d1d5db;background:#1f2937;}",

    // Step indicator
    ".ir-steps{",
      "display:flex;align-items:center;gap:8px;padding:16px 20px 8px;flex-shrink:0;",
    "}",
    ".ir-step{display:flex;align-items:center;gap:8px;flex:1;}",
    ".ir-step-circle{",
      "width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;",
      "font-size:11px;font-weight:700;transition:all 0.2s;flex-shrink:0;",
    "}",
    ".ir-step-circle--active{background:#2563eb;color:#fff;}",
    ".ir-step-circle--done{background:rgba(16,185,129,0.2);color:#34d399;}",
    ".ir-step-circle--pending{background:#1f2937;color:#4b5563;}",
    ".ir-step-label{font-size:12px;transition:color 0.2s;}",
    ".ir-step-label--active{color:#e5e7eb;}",
    ".ir-step-label--inactive{color:#4b5563;}",
    ".ir-step-line{flex:1;height:1px;background:#1f2937;}",

    // Scrollable body
    ".ir-body{padding:20px;overflow-y:auto;flex:1;min-height:0;-webkit-overflow-scrolling:touch;}",

    // Type selection cards
    ".ir-types{display:flex;flex-direction:column;gap:8px;}",
    ".ir-types-heading{font-size:13px;color:#9ca3af;margin:0 0 8px;}",
    ".ir-type-card{",
      "width:100%;display:flex;align-items:center;gap:12px;padding:12px 14px;",
      "border-radius:12px;border:1px solid;cursor:pointer;text-align:left;",
      "background:transparent;transition:all 0.2s;",
    "}",
    ".ir-type-card:focus{outline:2px solid #3b82f6;outline-offset:2px;}",
    ".ir-type-icon{font-size:20px;flex-shrink:0;width:28px;text-align:center;}",
    ".ir-type-info{flex:1;min-width:0;}",
    ".ir-type-label{font-size:14px;font-weight:500;color:#e5e7eb;}",
    ".ir-type-desc{font-size:12px;color:#6b7280;margin-top:1px;}",
    ".ir-type-check{color:#34d399;font-size:16px;flex-shrink:0;opacity:0;transition:opacity 0.15s;}",
    ".ir-type-check--visible{opacity:1;}",

    // Details step
    ".ir-field{margin-bottom:16px;}",
    ".ir-field:last-child{margin-bottom:0;}",
    ".ir-field-label{display:block;margin-bottom:6px;font-weight:500;font-size:12px;color:#9ca3af;}",
    ".ir-field-heading{font-size:14px;font-weight:600;color:#e5e7eb;margin:0 0 12px;}",

    // Context info bar
    ".ir-context-bar{",
      "font-size:12px;color:#6b7280;background:rgba(31,41,55,0.5);",
      "border-radius:8px;padding:8px 12px;display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px;",
    "}",
    ".ir-context-bar strong{color:#d1d5db;font-weight:600;}",

    // Section pills
    ".ir-pills{display:flex;flex-wrap:wrap;gap:6px;}",
    ".ir-pill{",
      "font-size:12px;padding:5px 12px;border-radius:8px;border:1px solid #374151;",
      "background:rgba(31,41,55,0.5);color:#9ca3af;cursor:pointer;",
      "transition:all 0.15s;",
    "}",
    ".ir-pill:hover{border-color:#4b5563;}",
    ".ir-pill--active{border-color:#3b82f6;background:rgba(59,130,246,0.2);color:#93c5fd;}",

    // Element inspector
    ".ir-inspect-btn{",
      "display:inline-flex;align-items:center;gap:6px;font-size:12px;",
      "padding:6px 14px;border-radius:8px;border:1px solid rgba(59,130,246,0.3);",
      "background:rgba(59,130,246,0.1);color:#60a5fa;cursor:pointer;",
      "transition:all 0.15s;",
    "}",
    ".ir-inspect-btn:hover{background:rgba(59,130,246,0.2);}",
    ".ir-inspect-btn svg{width:14px;height:14px;}",
    ".ir-element-info{",
      "font-size:12px;color:#9ca3af;background:rgba(31,41,55,0.3);",
      "border-radius:8px;padding:8px 10px;margin-top:8px;font-family:'SF Mono',Monaco,Consolas,'Liberation Mono',monospace;",
      "line-height:1.6;word-break:break-all;",
    "}",
    ".ir-element-tag{color:#60a5fa;}",
    ".ir-element-id{color:#fbbf24;}",
    ".ir-element-section{color:#4ade80;}",
    ".ir-element-text{color:#9ca3af;}",
    ".ir-element-href{color:rgba(96,165,250,0.6);}",

    // Textarea and inputs
    ".ir-textarea,.ir-input{",
      "width:100%;padding:10px 12px;border:1px solid #374151;border-radius:10px;",
      "font:inherit;font-size:14px;color:#e5e7eb;background:rgba(31,41,55,0.5);",
      "box-sizing:border-box;transition:border-color 0.15s;resize:vertical;",
    "}",
    ".ir-textarea:focus,.ir-input:focus{outline:none;border-color:rgba(59,130,246,0.5);}",
    ".ir-textarea{min-height:100px;max-height:200px;}",
    ".ir-textarea--short{min-height:60px;max-height:120px;}",
    ".ir-textarea::placeholder,.ir-input::placeholder{color:#4b5563;}",
    ".ir-char-count{font-size:11px;color:#4b5563;text-align:right;margin-top:4px;}",

    // Severity pills
    ".ir-severity{display:flex;gap:8px;}",
    ".ir-sev-pill{",
      "flex:1;text-align:center;padding:8px 4px;border-radius:8px;border:1px solid #374151;",
      "background:rgba(31,41,55,0.5);color:#6b7280;cursor:pointer;font-size:12px;font-weight:500;",
      "transition:all 0.15s;",
    "}",
    ".ir-sev-pill:hover{border-color:#4b5563;}",
    ".ir-sev-pill--active{border-color:#3b82f6;background:rgba(59,130,246,0.2);color:#93c5fd;}",

    // Review step
    ".ir-review-card{",
      "background:rgba(31,41,55,0.5);border-radius:12px;padding:16px;",
    "}",
    ".ir-review-row{display:flex;align-items:flex-start;gap:8px;margin-bottom:10px;}",
    ".ir-review-row:last-child{margin-bottom:0;}",
    ".ir-review-label{color:#6b7280;width:80px;flex-shrink:0;font-size:13px;}",
    ".ir-review-value{color:#e5e7eb;font-size:13px;flex:1;min-width:0;}",
    ".ir-review-value--mono{font-family:'SF Mono',Monaco,Consolas,monospace;font-size:12px;color:#d1d5db;word-break:break-all;}",
    ".ir-review-divider{border:none;border-top:1px solid #374151;margin:12px 0;}",
    ".ir-review-block-label{color:#6b7280;font-size:13px;margin-bottom:6px;}",
    ".ir-review-block-text{color:#e5e7eb;font-size:13px;white-space:pre-wrap;word-break:break-word;}",

    // Footer navigation
    ".ir-footer{",
      "display:flex;align-items:center;justify-content:space-between;",
      "padding:12px 20px;border-top:1px solid #1f2937;flex-shrink:0;",
    "}",
    ".ir-footer-back{",
      "display:flex;align-items:center;gap:4px;font-size:13px;color:#9ca3af;",
      "background:none;border:none;cursor:pointer;padding:6px 10px;border-radius:8px;",
      "transition:all 0.15s;",
    "}",
    ".ir-footer-back:hover{color:#e5e7eb;background:#1f2937;}",
    ".ir-footer-next,.ir-footer-submit{",
      "display:flex;align-items:center;gap:6px;font-size:13px;font-weight:600;color:#fff;",
      "background:#2563eb;border:none;padding:8px 18px;border-radius:10px;cursor:pointer;",
      "transition:all 0.15s;",
    "}",
    ".ir-footer-next:hover,.ir-footer-submit:hover{background:#3b82f6;}",
    ".ir-footer-next:disabled,.ir-footer-submit:disabled{background:#374151;color:#6b7280;cursor:not-allowed;}",
    ".ir-footer-version{font-size:10px;color:#4b5563;text-decoration:none;margin-left:auto;padding:2px 0;}",
    ".ir-footer-version:hover{color:#6b7280;}",

    // Status screens (loading, success, error)
    ".ir-status{padding:32px 20px;text-align:center;}",
    ".ir-status-icon{font-size:48px;margin-bottom:16px;}",
    ".ir-status-title{font-size:16px;font-weight:600;color:#f3f4f6;margin:0 0 8px;}",
    ".ir-status-msg{font-size:13px;color:#6b7280;margin:0 0 4px;}",
    ".ir-status-link{",
      "display:inline-flex;align-items:center;gap:6px;font-size:13px;color:#60a5fa;",
      "text-decoration:none;margin-top:12px;",
    "}",
    ".ir-status-link:hover{color:#93c5fd;}",
    ".ir-status-action{",
      "display:block;width:100%;margin-top:20px;padding:10px;border-radius:10px;",
      "background:#1f2937;border:none;color:#e5e7eb;font-size:14px;cursor:pointer;",
      "transition:background 0.15s;",
    "}",
    ".ir-status-action:hover{background:#374151;}",

    // Spinner
    ".ir-spinner{",
      "display:inline-block;width:28px;height:28px;",
      "border:3px solid #374151;border-top-color:#3b82f6;border-radius:50%;",
      "animation:ir-spin 0.6s linear infinite;",
    "}",
    "@keyframes ir-spin{to{transform:rotate(360deg);}}",

    // Inspect mode banner
    ".ir-inspect-banner{",
      "position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:2147483647;",
      "background:#2563eb;color:#fff;padding:10px 20px;border-radius:12px;",
      "box-shadow:0 4px 20px rgba(37,99,235,0.4);",
      "display:flex;align-items:center;gap:12px;font-size:14px;",
      "animation:ir-pulse-border 2s ease-in-out infinite;",
    "}",
    ".ir-inspect-banner svg{width:16px;height:16px;animation:ir-pulse-opacity 2s ease-in-out infinite;}",
    "@keyframes ir-pulse-opacity{0%,100%{opacity:1;}50%{opacity:0.5;}}",
    ".ir-inspect-cancel{",
      "font-size:12px;padding:4px 10px;background:rgba(255,255,255,0.2);",
      "border:none;color:#fff;border-radius:6px;cursor:pointer;",
      "transition:background 0.15s;",
    "}",
    ".ir-inspect-cancel:hover{background:rgba(255,255,255,0.3);}",

    // Error highlight on required fields
    ".ir-textarea--error{border-color:#ef4444 !important;}",

    // Two-column layout for details step
    ".ir-columns{display:grid;grid-template-columns:1fr 1fr;gap:0 20px;}",
    ".ir-col-span{grid-column:1/-1;}",

    // Mobile
    "@media(max-width:600px){",
      ".ir-modal{width:96%;max-width:none;border-radius:12px;}",
      ".ir-body{padding:16px;}",
      ".ir-header{padding:14px 16px;}",
      ".ir-footer{padding:10px 16px;}",
      ".ir-severity{flex-wrap:wrap;}",
      ".ir-sev-pill{flex:none;padding:6px 14px;}",
      ".ir-btn{padding:10px 16px;font-size:13px;}",
      ".ir-columns{grid-template-columns:1fr;}",
    "}",
  ].join("\n");

  // -------------------------------------------------------------------------
  // CSS injection
  // -------------------------------------------------------------------------

  function injectStyles() {
    if (document.getElementById("ir-styles")) {
      return;
    }
    var style = document.createElement("style");
    style.id = "ir-styles";
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  // -------------------------------------------------------------------------
  // DOM helpers
  // -------------------------------------------------------------------------

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      var keys = Object.keys(attrs);
      for (var i = 0; i < keys.length; i++) {
        var key = keys[i];
        var val = attrs[key];
        if (val === null || val === undefined) {
          continue;
        }
        if (key === "className") {
          node.className = val;
        } else if (key === "style" && typeof val === "object") {
          var styleKeys = Object.keys(val);
          for (var s = 0; s < styleKeys.length; s++) {
            node.style[styleKeys[s]] = val[styleKeys[s]];
          }
        } else if (key.indexOf("on") === 0 && typeof val === "function") {
          node.addEventListener(key.slice(2).toLowerCase(), val);
        } else if (key === "htmlFor") {
          node.setAttribute("for", val);
        } else {
          node.setAttribute(key, val);
        }
      }
    }
    if (children !== undefined && children !== null) {
      if (!Array.isArray(children)) {
        children = [children];
      }
      for (var c = 0; c < children.length; c++) {
        var child = children[c];
        if (typeof child === "string" || typeof child === "number") {
          node.appendChild(document.createTextNode(String(child)));
        } else if (child) {
          node.appendChild(child);
        }
      }
    }
    return node;
  }

  /** Remove all child nodes */
  function clearChildren(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  /** Safely inject an SVG constant (no user input) into an element */
  function injectSvg(parent, svgString) {
    var tmp = document.createElement("span");
    tmp.innerHTML = svgString; // safe: hardcoded SVG constants only
    if (tmp.firstChild) {
      parent.appendChild(tmp.firstChild);
    }
  }

  // -------------------------------------------------------------------------
  // Console error capture
  // -------------------------------------------------------------------------

  function installConsoleCapture() {
    origConsoleError = console.error;
    origConsoleWarn = console.warn;

    console.error = function () {
      var args = Array.prototype.slice.call(arguments);
      consoleErrors.push({
        level: "error",
        message: args.map(String).join(" "),
        ts: Date.now(),
      });
      if (consoleErrors.length > 10) {
        consoleErrors.shift();
      }
      origConsoleError.apply(console, args);
    };

    console.warn = function () {
      var args = Array.prototype.slice.call(arguments);
      consoleErrors.push({
        level: "warn",
        message: args.map(String).join(" "),
        ts: Date.now(),
      });
      if (consoleErrors.length > 10) {
        consoleErrors.shift();
      }
      origConsoleWarn.apply(console, args);
    };
  }

  function restoreConsoleCapture() {
    if (origConsoleError) {
      console.error = origConsoleError;
      origConsoleError = null;
    }
    if (origConsoleWarn) {
      console.warn = origConsoleWarn;
      origConsoleWarn = null;
    }
    consoleErrors = [];
  }

  // -------------------------------------------------------------------------
  // Fetch capture
  // -------------------------------------------------------------------------

  function installFetchCapture() {
    if (typeof window.fetch !== "function") {
      return;
    }
    origFetch = window.fetch;

    window.fetch = function () {
      var args = Array.prototype.slice.call(arguments);
      var url = typeof args[0] === "string" ? args[0] : (args[0] && args[0].url ? args[0].url : "");

      return origFetch.apply(window, args).then(function (response) {
        // Only capture /api/ calls, skip our own issue endpoints
        if (url.indexOf("/api/") === 0 && url.indexOf("/issues/") === -1) {
          try {
            var clone = response.clone();
            clone.text().then(function (body) {
              apiCalls.push({
                url: url,
                status: response.status,
                body: body.slice(0, 500),
                ts: Date.now(),
              });
              if (apiCalls.length > 5) {
                apiCalls.shift();
              }
            }).catch(function () { /* ignore clone errors */ });
          } catch (e) { /* ignore */ }
        }
        return response;
      });
    };
  }

  function restoreFetchCapture() {
    if (origFetch) {
      window.fetch = origFetch;
      origFetch = null;
    }
    apiCalls = [];
  }

  // -------------------------------------------------------------------------
  // Page context detection
  // -------------------------------------------------------------------------

  function detectPageType() {
    var path = window.location.pathname;
    if (path.indexOf("/profile/") === 0) return "profile";
    if (path.indexOf("/report/") === 0) return "profile";
    if (path === "/" || path === "") return "home";
    // Strip leading slash and return
    return path.replace(/^\//, "").replace(/\/.*$/, "") || "unknown";
  }

  function detectPageTitle() {
    var h1 = document.querySelector("h1");
    if (h1) {
      var text = (h1.textContent || "").trim();
      if (text && text.length < 100) return text;
    }
    return document.title || "";
  }

  function detectSections() {
    var sections = [];
    var seen = {};
    var dataSections = document.querySelectorAll("[data-section]");
    for (var i = 0; i < dataSections.length; i++) {
      var val = dataSections[i].getAttribute("data-section");
      if (val && !seen[val]) {
        sections.push(val);
        seen[val] = true;
      }
    }
    // Fallback: h2/h3 headings
    if (sections.length === 0) {
      var headings = document.querySelectorAll("h2, h3");
      for (var h = 0; h < headings.length; h++) {
        var text = (headings[h].textContent || "").trim();
        if (text && text.length < 50 && !seen[text]) {
          sections.push(text);
          seen[text] = true;
        }
      }
    }
    return sections;
  }

  // -------------------------------------------------------------------------
  // Element inspector
  // -------------------------------------------------------------------------

  function startInspect() {
    if (inspectActive) return;

    // Close modal first (before setting inspectActive, since closeModal
    // calls endInspect() when inspectActive is true)
    closeModal(true); // silent close, no button restore

    inspectActive = true;

    // Show banner
    inspectBannerEl = el("div", { className: "ir-inspect-banner ir-widget" }, []);
    injectSvg(inspectBannerEl, CROSSHAIR_SVG);
    inspectBannerEl.appendChild(document.createTextNode(" Click on the element that has the problem "));
    var cancelBtn = el("button", {
      className: "ir-inspect-cancel",
      onClick: cancelInspect,
    }, "Cancel");
    inspectBannerEl.appendChild(cancelBtn);
    document.body.appendChild(inspectBannerEl);

    document.body.style.cursor = "crosshair";

    inspectHandlers.click = function (e) {
      // Ignore clicks on our own widget elements (banner, cancel button, etc.)
      if (e.target.closest && e.target.closest(".ir-widget")) {
        return; // Let the event bubble normally to our cancel button
      }
      e.preventDefault();
      e.stopPropagation();
      captureElement(e.target);
    };

    inspectHandlers.mouseover = function (e) {
      if (e.target.closest && e.target.closest(".ir-widget")) return;
      e.target.style.outline = "2px solid #3b82f6";
      e.target.style.outlineOffset = "2px";
    };

    inspectHandlers.mouseout = function (e) {
      if (e.target.closest && e.target.closest(".ir-widget")) return;
      e.target.style.outline = "";
      e.target.style.outlineOffset = "";
    };

    document.addEventListener("click", inspectHandlers.click, true);
    document.addEventListener("mouseover", inspectHandlers.mouseover, true);
    document.addEventListener("mouseout", inspectHandlers.mouseout, true);
  }

  function captureElement(target) {
    // Get own direct text nodes
    var ownTextParts = [];
    var childNodes = target.childNodes;
    for (var i = 0; i < childNodes.length; i++) {
      if (childNodes[i].nodeType === 3) { // TEXT_NODE
        var t = (childNodes[i].textContent || "").trim();
        if (t) ownTextParts.push(t);
      }
    }
    var ownText = ownTextParts.join(" ").slice(0, 200) || null;
    var fullText = ((target.textContent || "").trim()).slice(0, 300) || null;

    // data-* attributes
    var dataAttrs = {};
    var attrs = target.attributes || [];
    for (var a = 0; a < attrs.length; a++) {
      if (attrs[a].name.indexOf("data-") === 0) {
        dataAttrs[attrs[a].name] = attrs[a].value;
      }
    }

    // Closest section
    var sectionParent = target.closest ? target.closest("[data-section]") : null;
    var closestSection = sectionParent ? sectionParent.getAttribute("data-section") : null;

    // className filtering
    var classStr = target.className || "";
    if (typeof classStr !== "string") classStr = classStr.toString ? classStr.toString() : "";
    var classes = classStr.split(/\s+/).filter(function (c) {
      return c && c.indexOf("_") !== 0 && c.length < 40;
    }).slice(0, 5).join(" ") || null;

    var info = {
      tag: target.tagName.toLowerCase(),
      id: target.id || null,
      className: classes,
      ownText: ownText,
      fullText: (fullText !== ownText) ? fullText : null,
      dataAttrs: Object.keys(dataAttrs).length > 0 ? dataAttrs : null,
      section: closestSection,
      href: target.href || (target.closest && target.closest("a") ? target.closest("a").href : null) || null,
      src: target.src || null,
    };

    state.elementInfo = info;

    // Auto-set section if found and not already set
    if (closestSection && !state.section) {
      state.section = closestSection;
    }

    endInspect();
    openModal();
  }

  function cancelInspect() {
    endInspect();
    openModal();
  }

  function endInspect() {
    if (!inspectActive) return;
    inspectActive = false;

    document.removeEventListener("click", inspectHandlers.click, true);
    document.removeEventListener("mouseover", inspectHandlers.mouseover, true);
    document.removeEventListener("mouseout", inspectHandlers.mouseout, true);
    document.body.style.cursor = "";

    // Clean up any remaining outlines
    var outlined = document.querySelectorAll("[style*='outline']");
    for (var i = 0; i < outlined.length; i++) {
      outlined[i].style.outline = "";
      outlined[i].style.outlineOffset = "";
    }

    if (inspectBannerEl && inspectBannerEl.parentNode) {
      inspectBannerEl.parentNode.removeChild(inspectBannerEl);
      inspectBannerEl = null;
    }
  }

  // -------------------------------------------------------------------------
  // Element info formatting
  // -------------------------------------------------------------------------

  function formatElementForSubmit(info) {
    var parts = ["[" + info.tag + "]"];
    if (info.id) parts.push("#" + info.id);
    if (info.section) parts.push('section="' + info.section + '"');
    if (info.href) parts.push('href="' + info.href + '"');
    if (info.src) parts.push('src="' + info.src + '"');
    if (info.dataAttrs) {
      var dkeys = Object.keys(info.dataAttrs);
      for (var i = 0; i < dkeys.length; i++) {
        parts.push(dkeys[i] + '="' + info.dataAttrs[dkeys[i]] + '"');
      }
    }
    if (info.ownText) parts.push('text: "' + info.ownText.slice(0, 150) + '"');
    else if (info.fullText) parts.push('children: "' + info.fullText.slice(0, 150) + '"');
    if (info.className) parts.push('class="' + info.className + '"');
    return parts.join(" ");
  }

  function buildElementInfoDisplay(info) {
    var box = el("div", { className: "ir-element-info" });
    // First line: tag, id, section
    var line1 = el("div");
    line1.appendChild(el("span", { className: "ir-element-tag" }, info.tag));
    if (info.id) {
      line1.appendChild(document.createTextNode(" "));
      line1.appendChild(el("span", { className: "ir-element-id" }, "#" + info.id));
    }
    if (info.section) {
      line1.appendChild(document.createTextNode(" in "));
      line1.appendChild(el("span", { className: "ir-element-section" }, '"' + info.section + '"'));
    }
    box.appendChild(line1);

    if (info.ownText) {
      box.appendChild(el("div", { className: "ir-element-text" }, info.ownText.slice(0, 100)));
    }
    if (info.href) {
      box.appendChild(el("div", { className: "ir-element-href" }, "\u2192 " + info.href));
    }
    return box;
  }

  // -------------------------------------------------------------------------
  // Issue formatting
  // -------------------------------------------------------------------------

  function formatIssueTitle(issueType, description) {
    var prefix = PREFIX_MAP[issueType] || "issue";
    var titleText = description.substring(0, 60).split("\n")[0];
    if (description.length > 60) {
      var lastSpace = titleText.lastIndexOf(" ");
      if (lastSpace > 20) {
        titleText = titleText.substring(0, lastSpace);
      }
      titleText += "...";
    }
    return prefix + ": " + titleText;
  }

  function formatIssueBody(payload) {
    var parts = [];

    // Summary
    parts.push("## Summary\n\n" + payload.description);

    // Context
    var contextLines = [];
    if (payload.page_url) contextLines.push("- **Page:** " + payload.page_url);
    if (payload.page_title) contextLines.push("- **Page Title:** " + payload.page_title);
    if (payload.section) contextLines.push("- **Section:** " + payload.section);
    if (payload.element_text) contextLines.push("- **Element:** " + payload.element_text);
    if (contextLines.length > 0) {
      parts.push("\n## Context\n\n" + contextLines.join("\n"));
    }

    // Expected behavior
    if (payload.expected_behavior) {
      parts.push("\n## Expected Behavior\n\n" + payload.expected_behavior);
    }

    // Console errors
    var recentErrors = consoleErrors.slice(-5);
    if (recentErrors.length > 0) {
      var errLines = recentErrors.map(function (e) {
        return "[" + e.level + "] " + e.message;
      });
      parts.push("\n## Console Errors\n\n```\n" + errLines.join("\n") + "\n```");
    }

    // API calls
    var recentCalls = apiCalls.slice(-3);
    if (recentCalls.length > 0) {
      var callLines = recentCalls.map(function (c) {
        return c.status + " " + c.url;
      });
      parts.push("\n## Recent API Calls\n\n```\n" + callLines.join("\n") + "\n```");
    }

    // Metadata
    var meta = [];
    meta.push("- **Type:** " + payload.type);
    meta.push("- **Severity:** " + payload.severity);
    if (payload.project_name) {
      meta.push("- **Project:** " + payload.project_name);
    }
    parts.push("\n## Metadata\n\n" + meta.join("\n"));

    // Footer
    var now = new Date();
    var ts = now.toISOString().replace("T", " ").substring(0, 16) + " UTC";
    parts.push("\n---\n*Reported via [issue-reporter](https://github.com/rayketcham-lab/issue-reporter) on " + ts + "*");

    return parts.join("\n");
  }

  function getLabelsForType(issueType, severity) {
    var labels = (LABEL_MAP[issueType] || []).slice();
    if (severity === "critical") {
      labels.push("critical");
    }
    return labels;
  }

  // -------------------------------------------------------------------------
  // Submission — two modes
  // -------------------------------------------------------------------------

  function buildPayload() {
    var typeObj = state.selectedType || {};
    var validIds = config.issueTypes.map(function (t) { return t.id; });
    var typeId = typeObj.id && validIds.indexOf(typeObj.id) !== -1 ? typeObj.id : "bug";
    return {
      type: typeId,
      severity: state.severity,
      description: state.description.trim(),
      expected_behavior: state.expectedBehavior.trim() || null,
      context: null,
      project_name: config.projectName || "",
      page_url: window.location.href,
      page_title: state.pageTitle || null,
      page_type: state.pageType || null,
      section: state.section || null,
      element_text: state.elementInfo ? formatElementForSubmit(state.elementInfo) : null,
      console_errors: consoleErrors.slice(-5).map(function (e) { return "[" + e.level + "] " + e.message; }).join("\n") || null,
      last_api_calls: apiCalls.slice(-3).map(function (c) { return c.status + " " + c.url; }).join("\n") || null,
    };
  }

  function submitToGitHub(payload) {
    var gh = config.github;
    var baseUrl = (gh.apiUrl || "https://api.github.com").replace(/\/+$/, "");
    var title = formatIssueTitle(payload.type, payload.description);
    var body = formatIssueBody(payload);
    var labels = getLabelsForType(payload.type, payload.severity);

    var apiPayload = { title: title, body: body };
    if (labels.length > 0) {
      apiPayload.labels = labels;
    }

    return fetch(baseUrl + "/repos/" + gh.repo + "/issues", {
      method: "POST",
      headers: {
        "Authorization": "Bearer " + gh.token,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(apiPayload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, status: res.status, data: data };
        });
      })
      .then(function (result) {
        if (result.ok) {
          return { success: true, url: result.data.html_url };
        }

        // Labels might not exist — retry without them
        if (result.status === 422 && labels.length > 0 &&
            JSON.stringify(result.data).indexOf("label") !== -1) {
          return fetch(baseUrl + "/repos/" + gh.repo + "/issues", {
            method: "POST",
            headers: {
              "Authorization": "Bearer " + gh.token,
              "Accept": "application/vnd.github+json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ title: title, body: body }),
          })
            .then(function (res2) { return res2.json(); })
            .then(function (data2) {
              if (data2.html_url) {
                return { success: true, url: data2.html_url };
              }
              return { success: false, error: data2.message || "GitHub API error" };
            });
        }

        return { success: false, error: result.data.message || "GitHub API error (HTTP " + result.status + ")" };
      });
  }

  function submitToEndpoint(payload) {
    var headers = { "Content-Type": "application/json" };
    if (config.token) {
      headers["Authorization"] = "Bearer " + config.token;
    }

    return fetch(config.endpoint, {
      method: "POST",
      headers: headers,
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (result.ok && result.data.success) {
          return { success: true, url: result.data.url };
        }
        return { success: false, error: result.data.error || "Server returned an error." };
      });
  }

  // -------------------------------------------------------------------------
  // Build floating button
  // -------------------------------------------------------------------------

  function createButton() {
    var posClass = config.position === "bottom-left" ? "ir-btn--bl" : "ir-btn--br";

    buttonEl = el("button", {
      className: "ir-btn " + posClass + " ir-widget",
      onClick: openModal,
      "aria-label": config.buttonText,
      type: "button",
    });

    // Bug icon
    injectSvg(buttonEl, BUG_ICON_SVG);
    buttonEl.appendChild(document.createTextNode(" " + config.buttonText));
    document.body.appendChild(buttonEl);
  }

  // -------------------------------------------------------------------------
  // Build modal content — multi-step wizard
  // -------------------------------------------------------------------------

  function getTypePrompts(typeId) {
    return CONTEXT_PROMPTS[typeId] || CONTEXT_PROMPTS.other;
  }

  function typeHasExpected(typeObj) {
    if (!typeObj) return false;
    if (typeof typeObj.showExpected === "boolean") return typeObj.showExpected;
    // Fallback: check ID
    var expTypes = { bug: true, data_issue: true, ui_bug: true, broken_link: true };
    return !!expTypes[typeObj.id];
  }

  // --- Step 0: Type Selection ---

  function buildStep0() {
    var container = el("div", { className: "ir-types" });
    container.appendChild(el("p", { className: "ir-types-heading" }, "What kind of issue are you experiencing?"));

    var types = config.issueTypes;
    for (var i = 0; i < types.length; i++) {
      (function (type) {
        var isSelected = state.selectedType && state.selectedType.id === type.id;
        var colorKey = type.color || "gray";
        var colors = TYPE_COLORS[colorKey] || TYPE_COLORS.gray;

        var card = el("button", {
          className: "ir-type-card",
          type: "button",
          style: {
            borderColor: isSelected ? colors.borderSelected : colors.border,
            background: isSelected ? colors.bgSelected : colors.bg,
            boxShadow: isSelected ? ("0 0 0 1px " + colors.ring) : "none",
          },
          onClick: function () {
            state.selectedType = type;
            renderBody();
          },
        });

        // Hover styles via mouseenter/leave
        card.addEventListener("mouseenter", function () {
          if (!(state.selectedType && state.selectedType.id === type.id)) {
            card.style.borderColor = colors.borderHover;
            card.style.background = colors.bgHover;
          }
        });
        card.addEventListener("mouseleave", function () {
          if (!(state.selectedType && state.selectedType.id === type.id)) {
            card.style.borderColor = colors.border;
            card.style.background = colors.bg;
          }
        });

        // Icon
        var iconSpan = el("span", { className: "ir-type-icon" });
        if (type.icon && (type.icon.indexOf("<svg") === 0 || type.icon.indexOf("<SVG") === 0)) {
          injectSvg(iconSpan, type.icon);
        } else {
          iconSpan.appendChild(document.createTextNode(type.icon || "\uD83D\uDCAC"));
        }
        card.appendChild(iconSpan);

        // Info
        var info = el("div", { className: "ir-type-info" });
        info.appendChild(el("div", { className: "ir-type-label" }, type.label));
        if (type.description) {
          info.appendChild(el("div", { className: "ir-type-desc" }, type.description));
        }
        card.appendChild(info);

        // Check mark
        var check = el("span", {
          className: "ir-type-check" + (isSelected ? " ir-type-check--visible" : ""),
        }, "\u2713");
        card.appendChild(check);

        container.appendChild(card);
      })(types[i]);
    }

    return container;
  }

  // --- Step 1: Details ---

  function buildStep1() {
    var typeObj = state.selectedType || {};
    var prompts = getTypePrompts(typeObj.id);
    var container = el("div");

    // Heading
    container.appendChild(el("h3", { className: "ir-field-heading" }, prompts.heading));

    // Context bar
    var ctxBar = el("div", { className: "ir-context-bar" });
    var pageSpan = el("span");
    pageSpan.appendChild(document.createTextNode("Page: "));
    pageSpan.appendChild(el("strong", null, state.pageType || "unknown"));
    ctxBar.appendChild(pageSpan);
    if (state.pageTitle) {
      var titleSpan = el("span");
      titleSpan.appendChild(document.createTextNode("Title: "));
      titleSpan.appendChild(el("strong", null, state.pageTitle));
      ctxBar.appendChild(titleSpan);
    }
    container.appendChild(ctxBar);

    // Section picker
    if (state.sections.length > 0) {
      var sectionField = el("div", { className: "ir-field" });
      sectionField.appendChild(el("label", { className: "ir-field-label" }, prompts.sectionLabel));
      var pills = el("div", { className: "ir-pills" });
      for (var s = 0; s < state.sections.length; s++) {
        (function (sec) {
          var isActive = state.section === sec;
          var pill = el("button", {
            className: "ir-pill" + (isActive ? " ir-pill--active" : ""),
            type: "button",
            onClick: function () {
              state.section = (state.section === sec) ? "" : sec;
              renderBody();
            },
          }, sec);
          pills.appendChild(pill);
        })(state.sections[s]);
      }
      sectionField.appendChild(pills);
      container.appendChild(sectionField);
    }

    // --- Two-column grid for details ---
    var grid = el("div", { className: "ir-columns" });

    // LEFT COLUMN: Description + Expected behavior
    var leftCol = el("div");

    // Description
    var descField = el("div", { className: "ir-field" });
    descField.appendChild(el("label", { className: "ir-field-label" }, prompts.descLabel));
    var descArea = el("textarea", {
      className: "ir-textarea",
      id: "ir-desc",
      placeholder: "Be as specific as you can...",
      "aria-label": "Description",
    });
    descArea.value = state.description;
    descArea.addEventListener("input", function () {
      state.description = descArea.value;
      var counter = document.getElementById("ir-desc-count");
      if (counter) {
        clearChildren(counter);
        counter.appendChild(document.createTextNode(state.description.length + "/5000"));
      }
    });
    descField.appendChild(descArea);
    descField.appendChild(el("div", { className: "ir-char-count", id: "ir-desc-count" }, state.description.length + "/5000"));
    leftCol.appendChild(descField);

    // Expected behavior (conditional)
    if (typeHasExpected(typeObj)) {
      var expField = el("div", { className: "ir-field" });
      expField.appendChild(el("label", { className: "ir-field-label" }, "What should happen instead?"));
      var expArea = el("textarea", {
        className: "ir-textarea ir-textarea--short",
        placeholder: "Describe what you expected...",
        "aria-label": "Expected behavior",
      });
      expArea.value = state.expectedBehavior;
      expArea.addEventListener("input", function () {
        state.expectedBehavior = expArea.value;
      });
      expField.appendChild(expArea);
      leftCol.appendChild(expField);
    }

    grid.appendChild(leftCol);

    // RIGHT COLUMN: Severity + Element inspector
    var rightCol = el("div");

    // Severity
    var sevField = el("div", { className: "ir-field" });
    sevField.appendChild(el("label", { className: "ir-field-label" }, "How bad is it?"));
    var sevRow = el("div", { className: "ir-severity" });
    for (var v = 0; v < SEVERITY_OPTIONS.length; v++) {
      (function (sev) {
        var isActive = state.severity === sev.id;
        var pill = el("button", {
          className: "ir-sev-pill" + (isActive ? " ir-sev-pill--active" : ""),
          type: "button",
          title: sev.desc,
          onClick: function () {
            state.severity = sev.id;
            renderBody();
          },
        }, sev.label);
        sevRow.appendChild(pill);
      })(SEVERITY_OPTIONS[v]);
    }
    sevField.appendChild(sevRow);
    rightCol.appendChild(sevField);

    // Element inspector
    var inspectField = el("div", { className: "ir-field" });
    inspectField.appendChild(el("label", { className: "ir-field-label" }, "Point to the problem (optional)"));

    var inspectRow = el("div", { style: { display: "flex", alignItems: "center", gap: "8px" } });
    var inspectBtn = el("button", {
      className: "ir-inspect-btn",
      type: "button",
      onClick: function () {
        startInspect();
      },
    });
    injectSvg(inspectBtn, CROSSHAIR_SVG);
    inspectBtn.appendChild(document.createTextNode(" Click an element"));
    inspectRow.appendChild(inspectBtn);

    if (state.elementInfo) {
      var clearElBtn = el("button", {
        className: "ir-inspect-btn",
        type: "button",
        style: { borderColor: "rgba(239,68,68,0.3)", color: "#f87171", background: "rgba(239,68,68,0.1)" },
        onClick: function () {
          state.elementInfo = null;
          renderBody();
        },
      }, "\u2715 Clear");
      inspectRow.appendChild(clearElBtn);
    }

    inspectField.appendChild(inspectRow);
    if (state.elementInfo) {
      inspectField.appendChild(buildElementInfoDisplay(state.elementInfo));
    }
    rightCol.appendChild(inspectField);

    grid.appendChild(rightCol);
    container.appendChild(grid);

    return container;
  }

  // --- Step 2: Review ---

  function buildStep2() {
    var container = el("div");
    container.appendChild(el("h3", { className: "ir-field-heading" }, "Review your report"));

    var card = el("div", { className: "ir-review-card" });

    // Type
    var typeLabel = state.selectedType ? state.selectedType.label : "Unknown";
    card.appendChild(buildReviewRow("Type:", typeLabel));

    // Page
    var pageVal = (state.pageType || "unknown") + (state.pageTitle ? " \u2014 " + state.pageTitle : "");
    card.appendChild(buildReviewRow("Page:", pageVal));

    // Section
    if (state.section) {
      card.appendChild(buildReviewRow("Section:", state.section));
    }

    // Element
    if (state.elementInfo) {
      var elemRow = el("div", { className: "ir-review-row" });
      elemRow.appendChild(el("span", { className: "ir-review-label" }, "Element:"));
      elemRow.appendChild(el("span", { className: "ir-review-value ir-review-value--mono" }, formatElementForSubmit(state.elementInfo)));
      card.appendChild(elemRow);
    }

    // Severity
    card.appendChild(buildReviewRow("Severity:", state.severity.charAt(0).toUpperCase() + state.severity.slice(1)));

    // Divider + description
    card.appendChild(el("hr", { className: "ir-review-divider" }));
    card.appendChild(el("div", { className: "ir-review-block-label" }, "Description:"));
    card.appendChild(el("div", { className: "ir-review-block-text" }, state.description));

    // Expected behavior
    if (state.expectedBehavior) {
      card.appendChild(el("hr", { className: "ir-review-divider" }));
      card.appendChild(el("div", { className: "ir-review-block-label" }, "Expected:"));
      card.appendChild(el("div", { className: "ir-review-block-text" }, state.expectedBehavior));
    }

    container.appendChild(card);
    return container;
  }

  function buildReviewRow(label, value) {
    var row = el("div", { className: "ir-review-row" });
    row.appendChild(el("span", { className: "ir-review-label" }, label));
    row.appendChild(el("span", { className: "ir-review-value" }, value));
    return row;
  }

  // --- Step indicator ---

  function buildStepIndicator() {
    var labels = ["Type", "Details", "Review"];
    var stepsRow = el("div", { className: "ir-steps" });

    for (var i = 0; i < labels.length; i++) {
      var stepDiv = el("div", { className: "ir-step" });

      var circleClass = "ir-step-circle ";
      var circleContent;
      if (i < state.step) {
        circleClass += "ir-step-circle--done";
        circleContent = "\u2713";
      } else if (i === state.step) {
        circleClass += "ir-step-circle--active";
        circleContent = String(i + 1);
      } else {
        circleClass += "ir-step-circle--pending";
        circleContent = String(i + 1);
      }

      stepDiv.appendChild(el("div", { className: circleClass }, circleContent));

      var labelClass = "ir-step-label " + (i === state.step ? "ir-step-label--active" : "ir-step-label--inactive");
      stepDiv.appendChild(el("span", { className: labelClass }, labels[i]));

      if (i < labels.length - 1) {
        stepDiv.appendChild(el("div", { className: "ir-step-line" }));
      }

      stepsRow.appendChild(stepDiv);
    }

    return stepsRow;
  }

  // --- Footer navigation ---

  function buildFooter() {
    var footer = el("div", { className: "ir-footer" });

    // Back button
    if (state.step > 0) {
      var backBtn = el("button", {
        className: "ir-footer-back",
        type: "button",
        onClick: function () {
          state.step--;
          renderContent();
        },
      }, ["\u2190 Back"]);
      footer.appendChild(backBtn);
    } else {
      footer.appendChild(el("div")); // spacer
    }

    // Next / Submit button
    if (state.step < 2) {
      var nextDisabled = (state.step === 0 && !state.selectedType);
      var nextBtn = el("button", {
        className: "ir-footer-next",
        type: "button",
        onClick: function () {
          if (state.step === 0 && !state.selectedType) return;
          state.step++;
          renderContent();
          // Focus description on step 1
          if (state.step === 1) {
            setTimeout(function () {
              var desc = document.getElementById("ir-desc");
              if (desc) desc.focus();
            }, 50);
          }
        },
      }, ["Next \u2192"]);
      if (nextDisabled) {
        nextBtn.disabled = true;
      }
      footer.appendChild(nextBtn);
    } else {
      var canSubmit = state.selectedType && state.description.trim().length >= 5;
      var submitBtn = el("button", {
        className: "ir-footer-submit",
        type: "button",
        onClick: handleSubmit,
      }, ["Submit Issue"]);
      if (!canSubmit) {
        submitBtn.disabled = true;
      }
      footer.appendChild(submitBtn);
    }

    // Version badge — right corner
    footer.appendChild(el("a", {
      className: "ir-footer-version",
      href: REPO_URL,
      target: "_blank",
      rel: "noopener noreferrer",
    }, "v" + VERSION));

    return footer;
  }

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  /** Render just the body + footer (preserves header) */
  function renderBody() {
    var bodyEl = document.getElementById("ir-body");
    var footerEl = document.getElementById("ir-footer");
    if (!bodyEl || !footerEl) return;

    clearChildren(bodyEl);
    clearChildren(footerEl);

    if (state.step === 0) {
      bodyEl.appendChild(buildStep0());
    } else if (state.step === 1) {
      bodyEl.appendChild(buildStep1());
    } else {
      bodyEl.appendChild(buildStep2());
    }

    var newFooter = buildFooter();
    // Move children from new footer into the existing footer container
    while (newFooter.firstChild) {
      footerEl.appendChild(newFooter.firstChild);
    }
  }

  /** Full re-render of modal content (steps + footer, or status screens) */
  function renderContent() {
    var content = document.getElementById("ir-content");
    if (!content) return;
    clearChildren(content);

    if (state.result !== null) {
      content.appendChild(buildResultScreen());
      return;
    }

    if (state.submitting) {
      content.appendChild(buildLoadingScreen());
      return;
    }

    // Step indicator
    content.appendChild(buildStepIndicator());

    // Body
    var body = el("div", { className: "ir-body", id: "ir-body" });
    if (state.step === 0) {
      body.appendChild(buildStep0());
    } else if (state.step === 1) {
      body.appendChild(buildStep1());
    } else {
      body.appendChild(buildStep2());
    }
    content.appendChild(body);

    // Footer
    var footer = el("div", { className: "ir-footer", id: "ir-footer" });
    var footerContent = buildFooter();
    while (footerContent.firstChild) {
      footer.appendChild(footerContent.firstChild);
    }
    content.appendChild(footer);
  }

  // -------------------------------------------------------------------------
  // Status screens
  // -------------------------------------------------------------------------

  function buildLoadingScreen() {
    return el("div", { className: "ir-status" }, [
      el("div", { className: "ir-spinner" }),
      el("p", { className: "ir-status-msg", style: { marginTop: "16px" } }, "Submitting..."),
    ]);
  }

  function buildResultScreen() {
    var result = state.result;
    if (result.success) {
      var children = [
        el("div", { className: "ir-status-icon", style: { color: "#34d399" } }, "\u2713"),
        el("p", { className: "ir-status-title" }, "Issue Created!"),
      ];
      if (result.url) {
        var link = el("a", {
          className: "ir-status-link",
          href: result.url,
          target: "_blank",
          rel: "noopener noreferrer",
        }, ["View on GitHub \u2197"]);
        children.push(link);
      }
      children.push(el("button", {
        className: "ir-status-action",
        type: "button",
        onClick: closeModal,
      }, "Done"));
      return el("div", { className: "ir-status" }, children);
    }

    // Error
    return el("div", { className: "ir-status" }, [
      el("div", { className: "ir-status-icon", style: { color: "#f87171" } }, "\u2717"),
      el("p", { className: "ir-status-title" }, "Something went wrong"),
      el("p", { className: "ir-status-msg" }, result.error || "Unknown error"),
      el("button", {
        className: "ir-status-action",
        type: "button",
        onClick: function () {
          state.result = null;
          state.submitting = false;
          renderContent();
        },
      }, "Try Again"),
    ]);
  }

  // -------------------------------------------------------------------------
  // Form submission
  // -------------------------------------------------------------------------

  function handleSubmit() {
    if (!state.selectedType || state.description.trim().length < 5) {
      return;
    }

    state.submitting = true;
    renderContent();

    var payload = buildPayload();
    var submitFn = config.github ? submitToGitHub : submitToEndpoint;

    submitFn(payload)
      .then(function (result) {
        state.submitting = false;
        state.result = result;
        renderContent();
      })
      .catch(function (err) {
        state.submitting = false;
        state.result = { success: false, error: "Network error: " + err.message };
        renderContent();
      });
  }

  // -------------------------------------------------------------------------
  // Modal create / open / close
  // -------------------------------------------------------------------------

  function createModal() {
    var titleText = "Report an Issue";
    if (config.projectName) {
      titleText = "Report Issue \u2014 " + config.projectName;
    }

    var headerLeft = el("div", { className: "ir-header-left" });
    headerLeft.appendChild(el("span", { className: "ir-header-icon" }, "\uD83D\uDCAC"));
    headerLeft.appendChild(el("h2", null, titleText));

    var closeBtn = el("button", {
      className: "ir-close",
      onClick: closeModal,
      "aria-label": "Close",
      type: "button",
    }, "\u2715");

    var header = el("div", { className: "ir-header" }, [headerLeft, closeBtn]);

    var content = el("div", { id: "ir-content" });

    modalEl = el("div", {
      className: "ir-modal ir-widget",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": titleText,
    }, [header, content]);

    // Prevent clicks inside modal from closing
    modalEl.addEventListener("click", function (e) {
      e.stopPropagation();
    });

    backdropEl = el("div", {
      className: "ir-backdrop ir-widget",
      onClick: function () {
        closeModal();
      },
    }, [modalEl]);

    document.body.appendChild(backdropEl);
  }

  function resetState() {
    state.step = 0;
    state.selectedType = null;
    state.description = "";
    state.section = "";
    state.elementInfo = null;
    state.expectedBehavior = "";
    state.severity = "medium";
    state.sections = [];
    state.pageTitle = "";
    state.pageType = "";
    state.submitting = false;
    state.result = null;
  }

  function openModal() {
    if (inspectActive) return;

    if (!modalEl) {
      createModal();
    }

    // Detect page context fresh each time we open (unless returning from inspect)
    if (state.step === 0 && !state.result) {
      // Full reset only when starting fresh
      if (!state.selectedType) {
        resetState();
      }
      state.sections = detectSections();
      state.pageTitle = detectPageTitle();
      state.pageType = detectPageType();
    } else if (state.step > 0) {
      // Returning from inspect or re-opening — refresh sections
      state.sections = detectSections();
    }

    renderContent();

    backdropEl.style.display = "flex";
    // Force reflow for animation
    void backdropEl.offsetHeight;
    backdropEl.classList.add("ir-backdrop--visible");

    if (buttonEl) {
      buttonEl.style.display = "none";
    }

    // Focus description on step 1
    if (state.step === 1) {
      setTimeout(function () {
        var desc = document.getElementById("ir-desc");
        if (desc) desc.focus();
      }, 250);
    }
  }

  function closeModal(silent) {
    if (inspectActive) {
      endInspect();
    }

    if (!backdropEl) return;
    backdropEl.classList.remove("ir-backdrop--visible");

    setTimeout(function () {
      if (backdropEl) {
        backdropEl.style.display = "none";
      }
      if (buttonEl && !silent) {
        buttonEl.style.display = "";
      }
    }, 250);

    // Reset state on close (unless silent close for inspect mode)
    if (!silent) {
      resetState();
    }
  }

  // -------------------------------------------------------------------------
  // Keyboard handling
  // -------------------------------------------------------------------------

  function handleKeydown(e) {
    if (e.key === "Escape") {
      if (inspectActive) {
        cancelInspect();
      } else if (backdropEl && backdropEl.classList.contains("ir-backdrop--visible")) {
        closeModal();
      }
    }
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  window.IssueReporter = {
    _initialized: false,

    /**
     * Initialize the issue reporter widget.
     *
     * @param {Object} options
     * @param {Object} [options.github] - Direct GitHub mode (no backend needed)
     * @param {string} options.github.repo - "owner/repo" (e.g. "acme/my-app")
     * @param {string} options.github.token - Fine-grained PAT with Issues read/write
     * @param {string} [options.endpoint] - Backend URL to POST reports to
     * @param {string} [options.projectName] - Project name shown in modal header
     * @param {string} [options.position="bottom-right"] - "bottom-right" or "bottom-left"
     * @param {string} [options.buttonText="Report Issue"] - Floating button text
     * @param {Array}  [options.issueTypes] - Array of {id, label, icon, description, color, showExpected}
     * @param {string} [options.token] - Auth token for endpoint mode (Bearer header)
     */
    init: function (options) {
      if (this._initialized) {
        console.warn("IssueReporter.init() called more than once. Ignoring.");
        return;
      }

      options = options || {};
      config = {
        github: options.github || null,
        endpoint: options.endpoint || DEFAULTS.endpoint,
        projectName: options.projectName || DEFAULTS.projectName,
        position: options.position || DEFAULTS.position,
        buttonText: options.buttonText || DEFAULTS.buttonText,
        issueTypes: options.issueTypes || DEFAULTS.issueTypes,
        token: options.token || DEFAULTS.token,
      };

      // Validate: need either github config or endpoint
      if (config.github) {
        if (!config.github.repo || !config.github.token) {
          console.error(
            "IssueReporter: github mode requires both repo and token. " +
            'Example: IssueReporter.init({ github: { repo: "owner/repo", token: "github_pat_xxxx" } }).'
          );
          return;
        }
        // Warn about token exposure on non-localhost origins
        var host = window.location.hostname;
        if (host !== "localhost" && host !== "127.0.0.1" && host !== "0.0.0.0" && host !== "[::1]") {
          console.warn(
            "IssueReporter: Direct GitHub mode exposes your PAT in page source. " +
            "This is fine for internal tools but for public sites, use backend mode instead. " +
            "See https://github.com/rayketcham-lab/issue-reporter#backend-integration"
          );
        }
      } else if (!config.endpoint) {
        console.error(
          "IssueReporter: provide either github (direct mode) or endpoint (backend mode). " +
          "See https://github.com/rayketcham-lab/issue-reporter for setup."
        );
        return;
      }

      injectStyles();
      installConsoleCapture();
      installFetchCapture();
      document.addEventListener("keydown", handleKeydown);

      // Wait for DOM to be ready
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", createButton);
      } else {
        createButton();
      }

      this._initialized = true;
    },

    /** Open the modal programmatically. */
    open: function () {
      if (!this._initialized) {
        console.error("IssueReporter: call init() first.");
        return;
      }
      openModal();
    },

    /** Close the modal programmatically. */
    close: function () {
      closeModal();
    },

    /** Remove the widget from the page entirely. */
    destroy: function () {
      // End inspect mode if active
      endInspect();

      // Remove DOM elements
      if (buttonEl && buttonEl.parentNode) {
        buttonEl.parentNode.removeChild(buttonEl);
      }
      if (backdropEl && backdropEl.parentNode) {
        backdropEl.parentNode.removeChild(backdropEl);
      }
      var styleEl = document.getElementById("ir-styles");
      if (styleEl && styleEl.parentNode) {
        styleEl.parentNode.removeChild(styleEl);
      }

      // Restore console and fetch wrappers
      restoreConsoleCapture();
      restoreFetchCapture();

      // Remove keydown listener
      document.removeEventListener("keydown", handleKeydown);

      // Clean up state
      buttonEl = null;
      modalEl = null;
      backdropEl = null;
      inspectBannerEl = null;
      config = {};
      resetState();
      this._initialized = false;
    },
  };
})();
