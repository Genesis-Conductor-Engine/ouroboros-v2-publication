// Node-oriented editable pro deck builder.
// Run this after editing SLIDES, SOURCES, and layout functions.
// The init script installs a sibling node_modules/@oai/artifact-tool package link
// and package.json with type=module for shell-run eval builders. Run with the
// Node executable from Codex workspace dependencies or the platform-appropriate
// command emitted by the init script.
// Do not use pnpm exec from the repo root or any Node binary whose module
// lookup cannot resolve the builder's sibling node_modules/@oai/artifact-tool.

const fs = await import("node:fs/promises");
const path = await import("node:path");
const { Presentation, PresentationFile } = await import("@oai/artifact-tool");

const W = 1280;
const H = 720;

const DECK_ID = "ouroboros-v2-publication";
const OUT_DIR = "/Users/Igor/.codex/worktrees/7869/TeamTitans/ouroboros-v2-publication/presentation/final";
const REF_DIR = "/Users/Igor/.codex/worktrees/7869/TeamTitans/ouroboros-v2-publication/presentation/reference-images";
const SCRATCH_DIR = path.resolve(process.env.PPTX_SCRATCH_DIR || path.join("tmp", "slides", DECK_ID));
const PREVIEW_DIR = path.join(SCRATCH_DIR, "preview");
const VERIFICATION_DIR = path.join(SCRATCH_DIR, "verification");
const INSPECT_PATH = path.join(SCRATCH_DIR, "inspect.ndjson");
const MAX_RENDER_VERIFY_LOOPS = 3;

const INK = "#101214";
const GRAPHITE = "#30363A";
const MUTED = "#687076";
const PAPER = "#F7F4ED";
const PAPER_96 = "#F7F4EDF5";
const WHITE = "#FFFFFF";
const ACCENT = "#27C47D";
const ACCENT_DARK = "#116B49";
const GOLD = "#D7A83D";
const CORAL = "#E86F5B";
const TRANSPARENT = "#00000000";

const TITLE_FACE = "Caladea";
const BODY_FACE = "Lato";
const MONO_FACE = "Aptos Mono";

const FALLBACK_PLATE_DATA_URL =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=";

const ROOT_DIR = "/Users/Igor/.codex/worktrees/7869/TeamTitans/ouroboros-v2-publication";
const RESULTS_DIR = path.join(ROOT_DIR, "results");
const SUMMARY_PATH = path.join(RESULTS_DIR, "benchmark_summary.json");
const FIGURES = {
  meanTtc: path.join(RESULTS_DIR, "mean_ttc.png"),
  lossCurves: path.join(RESULTS_DIR, "loss_curves.png"),
  eigenspectrum: path.join(RESULTS_DIR, "hessian_eigenspectrum.png"),
  pcaForce: path.join(RESULTS_DIR, "pca_repulsion_force.png"),
};

const SOURCES = {
  repo: "Genesis Conductor research package, fixed-seed outputs in results/.",
  benchmark: "src/ouroboros_v2_publication/benchmark.py",
  results: "results/benchmark_summary.json plus committed figures and CSVs.",
  constants: "Locked v8.8 device constants embedded in the benchmark module.",
};

const SLIDES = [
  {
    "kicker": "GENESIS CONDUCTOR",
    "title": "Ouroboros V2: Saddle-Point Escape on a 20D Ackley+saddle Landscape",
    "subtitle": "Publication deck for the fixed-seed benchmark comparing isotropic noise, HITL spatial repulsion, chiral p-bit annealing, and ER=EPR hypersphere escape.",
    "moment": "Spatial Barnes-Hut repulsion and ER=EPR both reach the convergence threshold immediately in the shipped run.",
    "notes": "Frame the deck as a reproducibility artifact, not a broad claim about all non-convex objectives.",
    "sources": ["repo", "results"]
  },
  {
    "kicker": "BENCHMARK DESIGN",
    "title": "Protocol and Deterministic Evaluation Surface",
    "subtitle": "One synthetic saddle, five escape strategies, ten fixed seeds, one convergence rule.",
    "notes": "Stress that the benchmark is intentionally narrow and uses a fixed seed window for falsifiability.",
    "sources": ["benchmark", "results"]
  },
  {
    "kicker": "SADDLE CHECK",
    "title": "The Trapped Point Is a Verified Saddle, Not a Flat Minimum",
    "subtitle": "Eigenstructure, PCA compression, and Barnes-Hut force all remain measurable in the reference run.",
    "notes": "Use this slide to justify why the escape step is necessary before resuming SGD.",
    "sources": ["results", "benchmark"]
  },
  {
    "kicker": "PRIMARY RESULT",
    "title": "Mean Steps-to-Convergence Separate the Escape Families",
    "subtitle": "Bare SGD remains trapped, Langevin escapes slowly, chiral improves the noise baseline, and ER=EPR matches the fastest route.",
    "notes": "This is the main quantitative slide. Keep the focus on fixed-seed ordering and not on the infinite speedup notation.",
    "sources": ["results"]
  },
  {
    "kicker": "TRAJECTORIES",
    "title": "Loss Curves Show Why Bare SGD Is Not a Credible Control",
    "subtitle": "The perturbation methods collapse under the loss threshold, while the unperturbed baseline stays parked at the saddle-adjacent basin.",
    "notes": "Point out that Random Langevin converges, but does so materially later than the strongest methods.",
    "sources": ["results"]
  },
  {
    "kicker": "FALSIFIABILITY",
    "title": "What Would Refute the Published Claim",
    "subtitle": "This repo defines a narrow rejection surface and reruns it in CI.",
    "notes": "Be explicit: if these checks fail on an unmodified rerun, the claim should be considered broken.",
    "sources": ["results", "constants", "repo"]
  },
  {
    "kicker": "PUBLICATION PACKAGE",
    "title": "Repo Contents and Reviewer Workflow",
    "subtitle": "Code, tests, CI, fixed outputs, citation metadata, and this deck live in one reproducible package.",
    "notes": "Close on the fact that the repo is intended to be cloned and challenged, not merely read.",
    "sources": ["repo", "benchmark", "results"]
  }
];

const inspectRecords = [];

async function pathExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function readImageBlob(imagePath) {
  const bytes = await fs.readFile(imagePath);
  if (!bytes.byteLength) {
    throw new Error(`Image file is empty: ${imagePath}`);
  }
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

async function normalizeImageConfig(config) {
  if (!config.path) {
    return config;
  }
  const { path: imagePath, ...rest } = config;
  return {
    ...rest,
    blob: await readImageBlob(imagePath),
  };
}

async function ensureDirs() {
  await fs.mkdir(OUT_DIR, { recursive: true });
  const obsoleteFinalArtifacts = [
    "preview",
    "verification",
    "inspect.ndjson",
    ["presentation", "proto.json"].join("_"),
    ["quality", "report.json"].join("_"),
  ];
  for (const obsolete of obsoleteFinalArtifacts) {
    await fs.rm(path.join(OUT_DIR, obsolete), { recursive: true, force: true });
  }
  await fs.mkdir(SCRATCH_DIR, { recursive: true });
  await fs.mkdir(PREVIEW_DIR, { recursive: true });
  await fs.mkdir(VERIFICATION_DIR, { recursive: true });
}

async function loadSummary() {
  return JSON.parse(await fs.readFile(SUMMARY_PATH, "utf8"));
}

function methodSummary(summary, methodName) {
  const method = summary.methods.find((item) => item.method === methodName);
  if (!method) {
    throw new Error(`Missing method summary for ${methodName}`);
  }
  return method;
}

function fmt(value, digits = 2, suffix = "") {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return "n/a";
  }
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function pct(value, digits = 1) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return "n/a";
  }
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

function titleCase(value) {
  return String(value || "")
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function addBackdrop(slide, slideNo, accent = ACCENT) {
  slide.background.fill = "#F7F4ED";
  addShape(slide, "rect", 0, 0, W, H, "#F7F4ED", TRANSPARENT, 0, { slideNo, role: "background" });
  addShape(slide, "rect", 0, 0, W, 84, "#EEE8DB", TRANSPARENT, 0, { slideNo, role: "background band" });
  addShape(slide, "rect", 930, 0, 350, H, "#EEF4EF", TRANSPARENT, 0, { slideNo, role: "background panel" });
  addShape(slide, "ellipse", 1050, 515, 180, 180, "#DDEDE1", TRANSPARENT, 0, { slideNo, role: "background orb" });
  addShape(slide, "rect", 64, 86, 8, 520, accent, TRANSPARENT, 0, { slideNo, role: "accent rule" });
}

function lineConfig(fill = TRANSPARENT, width = 0) {
  return { style: "solid", fill, width };
}

function recordShape(slideNo, shape, role, shapeType, x, y, w, h) {
  if (!slideNo) return;
  inspectRecords.push({
    kind: "shape",
    slide: slideNo,
    id: shape?.id || `slide-${slideNo}-${role}-${inspectRecords.length + 1}`,
    role,
    shapeType,
    bbox: [x, y, w, h],
  });
}

function addShape(slide, geometry, x, y, w, h, fill = TRANSPARENT, line = TRANSPARENT, lineWidth = 0, meta = {}) {
  const shape = slide.shapes.add({
    geometry,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: lineConfig(line, lineWidth),
  });
  recordShape(meta.slideNo, shape, meta.role || geometry, geometry, x, y, w, h);
  return shape;
}

function normalizeText(text) {
  if (Array.isArray(text)) {
    return text.map((item) => String(item ?? "")).join("\n");
  }
  return String(text ?? "");
}

function textLineCount(text) {
  const value = normalizeText(text);
  if (!value.trim()) {
    return 0;
  }
  return Math.max(1, value.split(/\n/).length);
}

function requiredTextHeight(text, fontSize, lineHeight = 1.18, minHeight = 8) {
  const lines = textLineCount(text);
  if (lines === 0) {
    return minHeight;
  }
  return Math.max(minHeight, lines * fontSize * lineHeight);
}

function assertTextFits(text, boxHeight, fontSize, role = "text") {
  const required = requiredTextHeight(text, fontSize);
  const tolerance = Math.max(2, fontSize * 0.08);
  if (normalizeText(text).trim() && boxHeight + tolerance < required) {
    throw new Error(
      `${role} text box is too short: height=${boxHeight.toFixed(1)}, required>=${required.toFixed(1)}, ` +
        `lines=${textLineCount(text)}, fontSize=${fontSize}, text=${JSON.stringify(normalizeText(text).slice(0, 90))}`,
    );
  }
}

function wrapText(text, widthChars) {
  const words = normalizeText(text).split(/\s+/).filter(Boolean);
  const lines = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > widthChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) {
    lines.push(current);
  }
  return lines.join("\n");
}

function recordText(slideNo, shape, role, text, x, y, w, h) {
  const value = normalizeText(text);
  inspectRecords.push({
    kind: "textbox",
    slide: slideNo,
    id: shape?.id || `slide-${slideNo}-${role}-${inspectRecords.length + 1}`,
    role,
    text: value,
    textPreview: value.replace(/\n/g, " | ").slice(0, 180),
    textChars: value.length,
    textLines: textLineCount(value),
    bbox: [x, y, w, h],
  });
}

function recordImage(slideNo, image, role, imagePath, x, y, w, h) {
  inspectRecords.push({
    kind: "image",
    slide: slideNo,
    id: image?.id || `slide-${slideNo}-${role}-${inspectRecords.length + 1}`,
    role,
    path: imagePath,
    bbox: [x, y, w, h],
  });
}

function applyTextStyle(box, text, size, color, bold, face, align, valign, autoFit, listStyle) {
  box.text = text;
  box.text.fontSize = size;
  box.text.color = color;
  box.text.bold = Boolean(bold);
  box.text.alignment = align;
  box.text.verticalAlignment = valign;
  box.text.typeface = face;
  box.text.insets = { left: 0, right: 0, top: 0, bottom: 0 };
  if (autoFit) {
    box.text.autoFit = autoFit;
  }
  if (listStyle) {
    box.text.style = "list";
  }
}

function addText(
  slide,
  slideNo,
  text,
  x,
  y,
  w,
  h,
  {
    size = 22,
    color = INK,
    bold = false,
    face = BODY_FACE,
    align = "left",
    valign = "top",
    fill = TRANSPARENT,
    line = TRANSPARENT,
    lineWidth = 0,
    autoFit = null,
    listStyle = false,
    checkFit = true,
    role = "text",
  } = {},
) {
  if (!checkFit && textLineCount(text) > 1) {
    throw new Error("checkFit=false is only allowed for single-line headers, footers, and captions.");
  }
  if (checkFit) {
    assertTextFits(text, h, size, role);
  }
  const box = addShape(slide, "rect", x, y, w, h, fill, line, lineWidth);
  applyTextStyle(box, text, size, color, bold, face, align, valign, autoFit, listStyle);
  recordText(slideNo, box, role, text, x, y, w, h);
  return box;
}

async function addImage(slide, slideNo, config, position, role, sourcePath = null) {
  const image = slide.images.add(await normalizeImageConfig(config));
  image.position = position;
  recordImage(slideNo, image, role, sourcePath || config.path || config.uri || "inline-data-url", position.left, position.top, position.width, position.height);
  return image;
}

async function addPlate(slide, slideNo, opacityPanel = false) {
  slide.background.fill = PAPER;
  const platePath = path.join(REF_DIR, `slide-${String(slideNo).padStart(2, "0")}.png`);
  if (await pathExists(platePath)) {
    await addImage(
      slide,
      slideNo,
      { path: platePath, fit: "cover", alt: `Text-free art-direction plate for slide ${slideNo}` },
      { left: 0, top: 0, width: W, height: H },
      "art plate",
      platePath,
    );
  } else {
    await addImage(
      slide,
      slideNo,
      { dataUrl: FALLBACK_PLATE_DATA_URL, fit: "cover", alt: `Fallback blank art plate for slide ${slideNo}` },
      { left: 0, top: 0, width: W, height: H },
      "fallback art plate",
      "fallback-data-url",
    );
  }
  if (opacityPanel) {
    addShape(slide, "rect", 0, 0, W, H, "#FFFFFFB8", TRANSPARENT, 0, { slideNo, role: "plate readability overlay" });
  }
}

function addHeader(slide, slideNo, kicker, idx, total) {
  addText(slide, slideNo, String(kicker || "").toUpperCase(), 64, 34, 430, 24, {
    size: 13,
    color: ACCENT_DARK,
    bold: true,
    face: MONO_FACE,
    checkFit: false,
    role: "header",
  });
  addText(slide, slideNo, `${String(idx).padStart(2, "0")} / ${String(total).padStart(2, "0")}`, 1114, 34, 104, 24, {
    size: 13,
    color: ACCENT_DARK,
    bold: true,
    face: MONO_FACE,
    align: "right",
    checkFit: false,
    role: "header",
  });
  addShape(slide, "rect", 64, 64, 1152, 2, INK, TRANSPARENT, 0, { slideNo, role: "header rule" });
  addShape(slide, "ellipse", 57, 57, 16, 16, ACCENT, INK, 2, { slideNo, role: "header marker" });
}

function addTitleBlock(slide, slideNo, title, subtitle = null, x = 64, y = 86, w = 780, dark = false) {
  const titleColor = dark ? PAPER : INK;
  const bodyColor = dark ? PAPER : GRAPHITE;
  addText(slide, slideNo, title, x, y, w, 142, {
    size: 40,
    color: titleColor,
    bold: true,
    face: TITLE_FACE,
    role: "title",
  });
  if (subtitle) {
    addText(slide, slideNo, subtitle, x + 2, y + 148, Math.min(w, 720), 70, {
      size: 19,
      color: bodyColor,
      face: BODY_FACE,
      role: "subtitle",
    });
  }
}

function addIconBadge(slide, slideNo, x, y, accent = ACCENT, kind = "signal") {
  addShape(slide, "ellipse", x, y, 54, 54, PAPER_96, INK, 1.2, { slideNo, role: "icon badge" });
  if (kind === "flow") {
    addShape(slide, "ellipse", x + 13, y + 18, 10, 10, accent, INK, 1, { slideNo, role: "icon glyph" });
    addShape(slide, "ellipse", x + 31, y + 27, 10, 10, accent, INK, 1, { slideNo, role: "icon glyph" });
    addShape(slide, "rect", x + 22, y + 25, 19, 3, INK, TRANSPARENT, 0, { slideNo, role: "icon glyph" });
  } else if (kind === "layers") {
    addShape(slide, "roundRect", x + 13, y + 15, 26, 13, accent, INK, 1, { slideNo, role: "icon glyph" });
    addShape(slide, "roundRect", x + 18, y + 24, 26, 13, GOLD, INK, 1, { slideNo, role: "icon glyph" });
    addShape(slide, "roundRect", x + 23, y + 33, 20, 10, CORAL, INK, 1, { slideNo, role: "icon glyph" });
  } else {
    addShape(slide, "rect", x + 16, y + 29, 6, 12, accent, TRANSPARENT, 0, { slideNo, role: "icon glyph" });
    addShape(slide, "rect", x + 25, y + 21, 6, 20, accent, TRANSPARENT, 0, { slideNo, role: "icon glyph" });
    addShape(slide, "rect", x + 34, y + 14, 6, 27, accent, TRANSPARENT, 0, { slideNo, role: "icon glyph" });
  }
}

function addCard(slide, slideNo, x, y, w, h, label, body, { accent = ACCENT, fill = PAPER_96, line = INK, iconKind = "signal" } = {}) {
  if (h < 156) {
    throw new Error(`Card is too short for editable pro-deck copy: height=${h.toFixed(1)}, minimum=156.`);
  }
  addShape(slide, "roundRect", x, y, w, h, fill, line, 1.2, { slideNo, role: `card panel: ${label}` });
  addShape(slide, "rect", x, y, 8, h, accent, TRANSPARENT, 0, { slideNo, role: `card accent: ${label}` });
  addIconBadge(slide, slideNo, x + 22, y + 24, accent, iconKind);
  addText(slide, slideNo, label, x + 88, y + 22, w - 108, 28, {
    size: 15,
    color: ACCENT_DARK,
    bold: true,
    face: MONO_FACE,
    role: "card label",
  });
  const wrapped = wrapText(body, Math.max(28, Math.floor(w / 13)));
  const bodyY = y + 86;
  const bodyH = h - (bodyY - y) - 22;
  if (bodyH < 54) {
    throw new Error(`Card body area is too short: height=${bodyH.toFixed(1)}, cardHeight=${h.toFixed(1)}, label=${JSON.stringify(label)}.`);
  }
  addText(slide, slideNo, wrapped, x + 24, bodyY, w - 48, bodyH, {
    size: 17,
    color: INK,
    face: BODY_FACE,
    role: `card body: ${label}`,
  });
}

function addMetricCard(slide, slideNo, x, y, w, h, metric, label, note = null, accent = ACCENT) {
  if (h < 132) {
    throw new Error(`Metric card is too short for editable pro-deck copy: height=${h.toFixed(1)}, minimum=132.`);
  }
  addShape(slide, "roundRect", x, y, w, h, PAPER_96, INK, 1.2, { slideNo, role: `metric panel: ${label}` });
  addShape(slide, "rect", x, y, w, 7, accent, TRANSPARENT, 0, { slideNo, role: `metric accent: ${label}` });
  addText(slide, slideNo, metric, x + 22, y + 24, w - 44, 54, {
    size: 34,
    color: INK,
    bold: true,
    face: TITLE_FACE,
    role: "metric value",
  });
  addText(slide, slideNo, label, x + 24, y + 82, w - 48, 38, {
    size: 16,
    color: GRAPHITE,
    face: BODY_FACE,
    role: "metric label",
  });
  if (note) {
    addText(slide, slideNo, note, x + 24, y + h - 42, w - 48, 22, {
      size: 10,
      color: MUTED,
      face: BODY_FACE,
      role: "metric note",
    });
  }
}

function addNotes(slide, body, sourceKeys) {
  const sourceLines = (sourceKeys || []).map((key) => `- ${SOURCES[key] || key}`).join("\n");
  slide.speakerNotes.setText(`${body || ""}\n\n[Sources]\n${sourceLines}`);
}

function addReferenceCaption(slide, slideNo) {
  addText(
    slide,
    slideNo,
    "All quantitative figures in this deck are regenerated from the repository's fixed-seed results directory.",
    64,
    674,
    980,
    22,
    {
      size: 10,
      color: MUTED,
      face: BODY_FACE,
      checkFit: false,
      role: "caption",
    },
  );
}

async function addFigurePanel(slide, slideNo, imagePath, x, y, w, h, title, caption = null) {
  addShape(slide, "roundRect", x, y, w, h, WHITE, INK, 1.2, { slideNo, role: `figure panel: ${title}` });
  addText(slide, slideNo, title, x + 22, y + 18, w - 44, 24, {
    size: 13,
    color: ACCENT_DARK,
    bold: true,
    face: MONO_FACE,
    checkFit: false,
    role: "figure title",
  });
  await addImage(
    slide,
    slideNo,
    { path: imagePath, fit: "contain", alt: title },
    { left: x + 18, top: y + 52, width: w - 36, height: h - 96 },
    `figure image: ${title}`,
    imagePath,
  );
  if (caption) {
    addText(slide, slideNo, caption, x + 22, y + h - 36, w - 44, 18, {
      size: 10,
      color: MUTED,
      face: BODY_FACE,
      checkFit: false,
      role: "figure caption",
    });
  }
}

async function slideCover(presentation) {
  const slideNo = 1;
  const data = SLIDES[0];
  const summary = await loadSummary();
  const hitl = methodSummary(summary, "HITL Spatial");
  const er = methodSummary(summary, "ER=EPR Hypersphere");
  const slide = presentation.slides.add();
  addBackdrop(slide, slideNo, ACCENT);
  addText(slide, slideNo, data.kicker, 86, 88, 520, 26, {
    size: 13,
    color: ACCENT_DARK,
    bold: true,
    face: MONO_FACE,
    role: "kicker",
  });
  addText(slide, slideNo, data.title, 82, 130, 700, 190, {
    size: 44,
    color: INK,
    bold: true,
    face: TITLE_FACE,
    role: "cover title",
  });
  addText(slide, slideNo, data.subtitle, 86, 326, 590, 94, {
    size: 18,
    color: GRAPHITE,
    face: BODY_FACE,
    role: "cover subtitle",
  });
  addShape(slide, "roundRect", 86, 456, 480, 130, PAPER_96, INK, 1.2, { slideNo, role: "cover moment panel" });
  addText(slide, slideNo, "Claim surface", 112, 478, 150, 18, {
    size: 13,
    color: ACCENT_DARK,
    bold: true,
    face: MONO_FACE,
    checkFit: false,
    role: "cover label",
  });
  addText(slide, slideNo, data.moment || "Replace with core idea", 112, 504, 410, 68, {
    size: 20,
    color: INK,
    bold: true,
    face: TITLE_FACE,
    role: "cover moment",
  });
  await addFigurePanel(
    slide,
    slideNo,
    FIGURES.meanTtc,
    720,
    106,
    470,
    508,
    "Fixed-seed benchmark snapshot",
    `HITL mean steps ${fmt(hitl.mean_steps)} | ER=EPR mean steps ${fmt(er.mean_steps)} | seeds 42..51`,
  );
  addText(slide, slideNo, "Poised for publication because the code, outputs, tests, and rejection criteria ship together.", 86, 606, 560, 28, {
    size: 15,
    color: GRAPHITE,
    face: BODY_FACE,
    checkFit: false,
    role: "cover footer",
  });
  addReferenceCaption(slide, slideNo);
  addNotes(slide, data.notes, data.sources);
}

async function slideProtocol(presentation, summary) {
  const slideNo = 2;
  const data = SLIDES[1];
  const slide = presentation.slides.add();
  addBackdrop(slide, slideNo, GOLD);
  addHeader(slide, slideNo, data.kicker, slideNo, SLIDES.length);
  addText(slide, slideNo, data.title, 64, 86, 760, 108, {
    size: 40,
    color: INK,
    bold: true,
    face: TITLE_FACE,
    role: "title",
  });
  addText(slide, slideNo, data.subtitle, 66, 190, 760, 24, {
    size: 17,
    color: GRAPHITE,
    face: BODY_FACE,
    checkFit: false,
    role: "subtitle",
  });
  addShape(slide, "roundRect", 1030, 106, 154, 104, WHITE, INK, 1.2, { slideNo, role: "thumbnail panel" });
  await addImage(
    slide,
    slideNo,
    { path: FIGURES.pcaForce, fit: "contain", alt: "PCA repulsion thumbnail" },
    { left: 1040, top: 118, width: 134, height: 80 },
    "thumbnail",
    FIGURES.pcaForce,
  );
  addMetricCard(slide, slideNo, 84, 236, 220, 148, `${summary.metadata.n_dim}D`, "Synthetic Ackley+saddle space", null, ACCENT);
  addMetricCard(slide, slideNo, 328, 236, 220, 148, String(summary.metadata.neighborhood_samples), "Neighborhood samples", null, GOLD);
  addMetricCard(slide, slideNo, 572, 236, 220, 148, "10", "Fixed random seeds", null, CORAL);
  addCard(
    slide,
    slideNo,
    84,
    426,
    352,
    232,
    "Landscape",
    "Ackley is smoothed only enough to keep the Hessian test stable, then injected with opposite curvatures across the two half-spaces.",
    { iconKind: "layers" },
  );
  addCard(
    slide,
    slideNo,
    464,
    426,
    352,
    232,
    "Escape families",
    "The comparison spans bare SGD, isotropic noise, PCA/Barnes-Hut HITL escape, chiral p-bit annealing, and ER=EPR hypersphere routing.",
    { accent: GOLD, iconKind: "flow" },
  );
  addCard(
    slide,
    slideNo,
    844,
    426,
    352,
    232,
    "Acceptance rule",
    "A run counts as converged only if post-escape SGD crosses loss < 1.0. The repo also checks saddle geometry, PCA variance, force magnitude, and constants.",
    { accent: CORAL, iconKind: "signal" },
  );
  addReferenceCaption(slide, slideNo);
  addNotes(slide, data.notes, data.sources);
}

async function slideSaddle(presentation, summary) {
  const slideNo = 3;
  const data = SLIDES[2];
  const slide = presentation.slides.add();
  addBackdrop(slide, slideNo, ACCENT_DARK);
  addHeader(slide, slideNo, data.kicker, slideNo, SLIDES.length);
  addText(slide, slideNo, data.title, 64, 86, 860, 108, {
    size: 40,
    color: INK,
    bold: true,
    face: TITLE_FACE,
    role: "title",
  });
  addText(slide, slideNo, data.subtitle, 66, 190, 760, 24, {
    size: 17,
    color: GRAPHITE,
    face: BODY_FACE,
    checkFit: false,
    role: "subtitle",
  });
  await addFigurePanel(
    slide,
    slideNo,
    FIGURES.eigenspectrum,
    64,
    230,
    540,
    270,
    "Hessian eigenvalue spectrum",
    "Positive and negative curvature coexist at the trapped point.",
  );
  await addFigurePanel(
    slide,
    slideNo,
    FIGURES.pcaForce,
    636,
    228,
    580,
    270,
    "PCA neighborhood and Barnes-Hut force",
    "The local cloud compresses well into 3D and still produces a non-zero escape force.",
  );
  addMetricCard(slide, slideNo, 84, 530, 340, 142, fmt(summary.reference_context.spectral_gap, 2), "Spectral gap |min negative eigenvalue|", null, ACCENT);
  addMetricCard(slide, slideNo, 470, 530, 340, 142, pct(summary.reference_context.pca_variance_captured, 1), "PCA variance captured", null, GOLD);
  addMetricCard(slide, slideNo, 856, 530, 340, 142, fmt(summary.reference_context.barnes_hut_force_norm, 1), "Barnes-Hut force norm", null, CORAL);
  addReferenceCaption(slide, slideNo);
  addNotes(slide, data.notes, data.sources);
}

async function slideResults(presentation, summary) {
  const slideNo = 4;
  const data = SLIDES[3];
  const slide = presentation.slides.add();
  const hitl = methodSummary(summary, "HITL Spatial");
  const chiral = methodSummary(summary, "Chiral p-bit");
  const er = methodSummary(summary, "ER=EPR Hypersphere");
  addBackdrop(slide, slideNo, GOLD);
  addHeader(slide, slideNo, data.kicker, slideNo, SLIDES.length);
  addText(slide, slideNo, data.title, 64, 86, 860, 108, {
    size: 40,
    color: INK,
    bold: true,
    face: TITLE_FACE,
    role: "title",
  });
  addText(slide, slideNo, data.subtitle, 66, 190, 820, 24, {
    size: 17,
    color: GRAPHITE,
    face: BODY_FACE,
    checkFit: false,
    role: "subtitle",
  });
  await addFigurePanel(
    slide,
    slideNo,
    FIGURES.meanTtc,
    64,
    228,
    720,
    380,
    "Mean steps-to-convergence by method",
    "Bar chart generated directly from the fixed-seed benchmark summary.",
  );
  addMetricCard(slide, slideNo, 836, 234, 340, 132, fmt(hitl.mean_steps, 2), "HITL Spatial mean steps", null, ACCENT);
  addMetricCard(slide, slideNo, 836, 390, 340, 132, summary.speedups.chiral_vs_random_langevin.display, "Chiral vs Random Langevin", null, GOLD);
  addMetricCard(slide, slideNo, 836, 546, 340, 132, fmt(er.mean_steps, 2), "ER=EPR mean steps", null, CORAL);
  addNotes(slide, data.notes, data.sources);
}

async function slideCurves(presentation, summary) {
  const slideNo = 5;
  const data = SLIDES[4];
  const slide = presentation.slides.add();
  const bare = methodSummary(summary, "Bare SGD");
  const random = methodSummary(summary, "Random Langevin");
  const chiral = methodSummary(summary, "Chiral p-bit");
  addBackdrop(slide, slideNo, CORAL);
  addHeader(slide, slideNo, data.kicker, slideNo, SLIDES.length);
  addText(slide, slideNo, data.title, 64, 86, 860, 108, {
    size: 40,
    color: INK,
    bold: true,
    face: TITLE_FACE,
    role: "title",
  });
  addText(slide, slideNo, data.subtitle, 66, 190, 820, 24, {
    size: 17,
    color: GRAPHITE,
    face: BODY_FACE,
    checkFit: false,
    role: "subtitle",
  });
  await addFigurePanel(
    slide,
    slideNo,
    FIGURES.lossCurves,
    64,
    228,
    740,
    380,
    "Mean loss curves with standard-deviation shading",
    "All curves are measured after the escape perturbation and resumed SGD.",
  );
  addCard(
    slide,
    slideNo,
    844,
    228,
    352,
    166,
    "Bare SGD",
    `${bare.converged_runs}/${bare.runs} converge; mean final loss stays at ${fmt(bare.mean_final_loss, 2)}.`,
    { accent: CORAL, iconKind: "signal" },
  );
  addCard(
    slide,
    slideNo,
    844,
    391,
    352,
    166,
    "Random vs Chiral",
    `Random averages ${fmt(random.mean_steps, 1)} steps; chiral lowers that to ${fmt(chiral.mean_steps, 1)}.`,
    { accent: GOLD, iconKind: "flow" },
  );
  addCard(
    slide,
    slideNo,
    844,
    548,
    352,
    166,
    "Fastest methods",
    "HITL and ER=EPR cross threshold immediately.",
    { accent: ACCENT, iconKind: "layers" },
  );
  addNotes(slide, data.notes, data.sources);
}

async function slideFalsifiability(presentation, summary) {
  const slideNo = 6;
  const data = SLIDES[5];
  const slide = presentation.slides.add();
  addBackdrop(slide, slideNo, ACCENT_DARK);
  addHeader(slide, slideNo, data.kicker, slideNo, SLIDES.length);
  addText(slide, slideNo, data.title, 64, 86, 820, 108, {
    size: 40,
    color: INK,
    bold: true,
    face: TITLE_FACE,
    role: "title",
  });
  addText(slide, slideNo, data.subtitle, 66, 190, 760, 24, {
    size: 17,
    color: GRAPHITE,
    face: BODY_FACE,
    checkFit: false,
    role: "subtitle",
  });
  addShape(slide, "roundRect", 1030, 106, 154, 104, WHITE, INK, 1.2, { slideNo, role: "thumbnail panel" });
  await addImage(
    slide,
    slideNo,
    { path: FIGURES.meanTtc, fit: "contain", alt: "mean ttc thumbnail" },
    { left: 1040, top: 118, width: 134, height: 80 },
    "thumbnail",
    FIGURES.meanTtc,
  );
  addCard(
    slide,
    slideNo,
    84,
    250,
    352,
    236,
    "Reproduce",
    "Use Python 3.10+, install the package, rerun seeds 42..51, and compare the regenerated results/ directory against the committed snapshot.",
    { accent: ACCENT, iconKind: "flow" },
  );
  addCard(
    slide,
    slideNo,
    464,
    250,
    352,
    236,
    "Reject",
    "The claim fails if any validation flips, if HITL or Chiral stops converging, or if ER=EPR no longer beats Chiral.",
    { accent: GOLD, iconKind: "signal" },
  );
  addCard(
    slide,
    slideNo,
    844,
    250,
    352,
    236,
    "CI guardrail",
    "GitHub Actions reruns tests and the fixed-seed benchmark on every push and pull request, then uploads fresh outputs.",
    { accent: CORAL, iconKind: "layers" },
  );
  addMetricCard(slide, slideNo, 84, 530, 340, 142, fmt(summary.locked_constants.j_ij_mean, 3), "Locked J_ij mean", null, ACCENT);
  addMetricCard(slide, slideNo, 470, 530, 340, 142, fmt(summary.locked_constants.delta_v_ev, 5), "Barrier ΔV (eV)", null, GOLD);
  addMetricCard(slide, slideNo, 856, 530, 340, 142, "5.23 ps", "Device time constant", null, CORAL);
  addNotes(slide, data.notes, data.sources);
}

async function slideRepo(presentation) {
  const slideNo = 7;
  const data = SLIDES[6];
  const slide = presentation.slides.add();
  addBackdrop(slide, slideNo, ACCENT);
  addHeader(slide, slideNo, data.kicker, slideNo, SLIDES.length);
  addText(slide, slideNo, data.title, 64, 86, 860, 108, {
    size: 40,
    color: INK,
    bold: true,
    face: TITLE_FACE,
    role: "title",
  });
  addText(slide, slideNo, data.subtitle, 66, 190, 840, 24, {
    size: 17,
    color: GRAPHITE,
    face: BODY_FACE,
    checkFit: false,
    role: "subtitle",
  });
  addShape(slide, "roundRect", 1030, 106, 154, 104, WHITE, INK, 1.2, { slideNo, role: "thumbnail panel" });
  await addImage(
    slide,
    slideNo,
    { path: FIGURES.lossCurves, fit: "contain", alt: "loss curves thumbnail" },
    { left: 1040, top: 118, width: 134, height: 80 },
    "thumbnail",
    FIGURES.lossCurves,
  );
  addCard(
    slide,
    slideNo,
    84,
    240,
    520,
    210,
    "Code path",
    "The benchmark logic, finite-difference checks, escape solvers, and output writers live in src/ouroboros_v2_publication/benchmark.py.",
    { accent: ACCENT, iconKind: "flow" },
  );
  addCard(
    slide,
    slideNo,
    648,
    240,
    548,
    210,
    "Machine-readable outputs",
    "results/ ships the summary JSON, per-seed CSV, mean loss curves CSV, and the four publication figures used in this deck.",
    { accent: GOLD, iconKind: "layers" },
  );
  addCard(
    slide,
    slideNo,
    84,
    460,
    520,
    210,
    "Reviewer workflow",
    "Clone, install, run the benchmark, inspect the CSVs, read FALSIFIABILITY.md, and compare regenerated results against the committed publication snapshot.",
    { accent: CORAL, iconKind: "signal" },
  );
  addCard(
    slide,
    slideNo,
    648,
    460,
    548,
    210,
    "Publication metadata",
    "The repo includes CITATION.cff, an MIT license, CI, and this editable deck so the benchmark can be cited, rerun, and challenged without hidden steps.",
    { accent: ACCENT_DARK, iconKind: "flow" },
  );
  addNotes(slide, data.notes, data.sources);
}

async function createDeck() {
  await ensureDirs();
  const summary = await loadSummary();
  const presentation = Presentation.create({ slideSize: { width: W, height: H } });
  await slideCover(presentation);
  await slideProtocol(presentation, summary);
  await slideSaddle(presentation, summary);
  await slideResults(presentation, summary);
  await slideCurves(presentation, summary);
  await slideFalsifiability(presentation, summary);
  await slideRepo(presentation);
  return presentation;
}

async function saveBlobToFile(blob, filePath) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  await fs.writeFile(filePath, bytes);
}

async function writeInspectArtifact(presentation) {
  inspectRecords.unshift({
    kind: "deck",
    id: DECK_ID,
    slideCount: presentation.slides.count,
    slideSize: { width: W, height: H },
  });
  presentation.slides.items.forEach((slide, index) => {
    inspectRecords.splice(index + 1, 0, {
      kind: "slide",
      slide: index + 1,
      id: slide?.id || `slide-${index + 1}`,
    });
  });
  const lines = inspectRecords.map((record) => JSON.stringify(record)).join("\n") + "\n";
  await fs.writeFile(INSPECT_PATH, lines, "utf8");
}

async function currentRenderLoopCount() {
  const logPath = path.join(VERIFICATION_DIR, "render_verify_loops.ndjson");
  if (!(await pathExists(logPath))) return 0;
  const previous = await fs.readFile(logPath, "utf8");
  return previous.split(/\r?\n/).filter((line) => line.trim()).length;
}

async function nextRenderLoopNumber() {
  return (await currentRenderLoopCount()) + 1;
}

async function appendRenderVerifyLoop(presentation, previewPaths, pptxPath) {
  const logPath = path.join(VERIFICATION_DIR, "render_verify_loops.ndjson");
  const priorCount = await currentRenderLoopCount();
  const record = {
    kind: "render_verify_loop",
    deckId: DECK_ID,
    loop: priorCount + 1,
    maxLoops: MAX_RENDER_VERIFY_LOOPS,
    capReached: priorCount + 1 >= MAX_RENDER_VERIFY_LOOPS,
    timestamp: new Date().toISOString(),
    slideCount: presentation.slides.count,
    previewCount: previewPaths.length,
    previewDir: PREVIEW_DIR,
    inspectPath: INSPECT_PATH,
    pptxPath,
  };
  await fs.appendFile(logPath, JSON.stringify(record) + "\n", "utf8");
  return record;
}

async function verifyAndExport(presentation) {
  await ensureDirs();
  const nextLoop = await nextRenderLoopNumber();
  if (nextLoop > MAX_RENDER_VERIFY_LOOPS) {
    throw new Error(
      `Render/verify/fix loop cap reached: ${MAX_RENDER_VERIFY_LOOPS} total renders are allowed. ` +
        "Do not rerender; note any remaining visual issues in the final response.",
    );
  }
  await writeInspectArtifact(presentation);
  const previewPaths = [];
  for (let idx = 0; idx < presentation.slides.items.length; idx += 1) {
    const slide = presentation.slides.items[idx];
    const preview = await presentation.export({ slide, format: "png", scale: 1 });
    const previewPath = path.join(PREVIEW_DIR, `slide-${String(idx + 1).padStart(2, "0")}.png`);
    await saveBlobToFile(preview, previewPath);
    previewPaths.push(previewPath);
  }
  const pptxBlob = await PresentationFile.exportPptx(presentation);
  const pptxPath = path.join(OUT_DIR, "output.pptx");
  await pptxBlob.save(pptxPath);
  const loopRecord = await appendRenderVerifyLoop(presentation, previewPaths, pptxPath);
  return { pptxPath, loopRecord };
}

const presentation = await createDeck();
const result = await verifyAndExport(presentation);
console.log(result.pptxPath);
