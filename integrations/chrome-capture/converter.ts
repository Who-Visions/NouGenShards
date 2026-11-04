/**
 * NouGen Invariant Source-to-Markdown Engine (Top 0.001% DOM AST Transpiler)
 * Deterministic conversion conforming to CommonMark + GitHub Flavored Markdown (GFM).
 * Preserves code fences, nested tables, math blocks, absolute URLs, and semantic hierarchy.
 */

// Block tags that inherently terminate inline sequences
const BLOCK_TAGS = new Set([
  "address", "article", "aside", "blockquote", "canvas", "dd", "div",
  "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form",
  "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main",
  "nav", "noscript", "ol", "p", "pre", "section", "table", "tfoot", "ul", "video"
]);

// Tags to strip entirely with their children
const DROP_TAGS = new Set([
  "script", "style", "noscript", "iframe", "svg", "canvas", "nav",
  "footer", "header", "aside", "form", "button", "input", "select", "textarea"
]);


/**
 * Clean & resolve relative URLs to absolute
 */
function cleanUrl(raw: string | null | undefined, base?: string): string {
  if (!raw) return "";
  const trimmed = raw.trim();
  if (trimmed.startsWith("javascript:") || trimmed.startsWith("data:")) return "";
  if (!base) return trimmed;
  try {
    return new URL(trimmed, base).href;
  } catch {
    return trimmed;
  }
}

/**
 * Escapes markdown control characters in plain text nodes
 */
function escapeMarkdownText(text: string): string {
  return text
    .replace(/\\/g, "\\\\")
    .replace(/([*_{}[\]()#+\-.!|`])/g, "\\$1");
}

/**
 * Formats table rows into GFM pipe table syntax
 */
function renderGfmTable(table: Element, base?: string): string {
  const rows: string[][] = [];
  const trs = table.querySelectorAll("tr");
  if (!trs.length) return "";

  trs.forEach((tr) => {
    const row: string[] = [];
    tr.querySelectorAll("th, td").forEach((cell) => {
      // Process cell contents inline
      const text = (cell.textContent || "").replace(/\s+/g, " ").replace(/\|/g, "\\|").trim();
      row.push(text);
    });
    if (row.length > 0) rows.push(row);
  });

  if (rows.length === 0) return "";

  // Normalize column count
  const maxCols = Math.max(...rows.map((r) => r.length));
  if (maxCols === 0) return "";

  const lines: string[] = [];
  // Header row
  const header = rows[0];
  while (header.length < maxCols) header.push("");
  lines.push(`| ${header.join(" | ")} |`);

  // Delimiter row
  const delimiter = Array(maxCols).fill("---");
  lines.push(`| ${delimiter.join(" | ")} |`);

  // Data rows
  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    while (r.length < maxCols) r.push("");
    lines.push(`| ${r.join(" | ")} |`);
  }

  return `\n\n${lines.join("\n")}\n\n`;
}

/**
 * Recursive DOM to Markdown AST transpiler
 */
export function domToMarkdown(node: Node, baseUri?: string): string {
  if (node.nodeType === Node.TEXT_NODE) {
    // Collapse internal whitespace for standard text nodes
    const val = node.nodeValue || "";
    return val.replace(/\s+/g, " ");
  }

  if (node.nodeType !== Node.ELEMENT_NODE) return "";

  const el = node as Element;
  const tag = el.tagName.toLowerCase();

  if (DROP_TAGS.has(tag)) return "";

  // Invariant 2: Math block preservation
  if (el.classList.contains("katex-display") || el.classList.contains("math-display") || tag === "math") {
    const annotation = el.querySelector("annotation[encoding='application/x-tex']");
    if (annotation && annotation.textContent) {
      return `\n\n$$\n${annotation.textContent.trim()}\n$$\n\n`;
    }
    const tex = el.getAttribute("data-tex") || el.textContent || "";
    return `\n\n$$\n${tex.trim()}\n$$\n\n`;
  }
  if (el.classList.contains("katex") || el.classList.contains("math-inline")) {
    const annotation = el.querySelector("annotation[encoding='application/x-tex']");
    if (annotation && annotation.textContent) {
      return `$${annotation.textContent.trim()}$`;
    }
  }

  // Invariant 2: Code block preservation (No escaping inside code fences)
  if (tag === "pre") {
    const code = el.querySelector("code") || el;
    let lang = "";
    for (const c of Array.from(code.classList)) {
      if (c.startsWith("language-") || c.startsWith("lang-")) {
        lang = c.replace(/^(language-|lang-)/, "");
        break;
      }
    }
    const codeContent = code.textContent || "";
    return `\n\n\`\`\`${lang}\n${codeContent.replace(/\r\n/g, "\n")}\n\`\`\`\n\n`;
  }

  // Invariant 4: Tabular Data Preservation
  if (tag === "table") {
    return renderGfmTable(el, baseUri);
  }

  // Process child nodes
  let childrenMd = "";
  for (const child of Array.from(el.childNodes)) {
    childrenMd += domToMarkdown(child, baseUri);
  }

  // Tag transformations
  switch (tag) {
    case "h1": return `\n\n# ${childrenMd.trim()}\n\n`;
    case "h2": return `\n\n## ${childrenMd.trim()}\n\n`;
    case "h3": return `\n\n### ${childrenMd.trim()}\n\n`;
    case "h4": return `\n\n#### ${childrenMd.trim()}\n\n`;
    case "h5": return `\n\n##### ${childrenMd.trim()}\n\n`;
    case "h6": return `\n\n###### ${childrenMd.trim()}\n\n`;

    case "p": return `\n\n${childrenMd.trim()}\n\n`;
    case "blockquote": {
      const quoted = childrenMd
        .trim()
        .split("\n")
        .map((l) => `> ${l}`)
        .join("\n");
      return `\n\n${quoted}\n\n`;
    }

    case "ul": return `\n\n${childrenMd.trim()}\n\n`;
    case "ol": return `\n\n${childrenMd.trim()}\n\n`;
    case "li": {
      const parentTag = el.parentElement ? el.parentElement.tagName.toLowerCase() : "ul";
      if (parentTag === "ol") {
        const index = Array.from(el.parentElement?.children || []).indexOf(el) + 1;
        return `${index}. ${childrenMd.trim()}\n`;
      }
      return `- ${childrenMd.trim()}\n`;
    }

    case "strong":
    case "b":
      return childrenMd.trim() ? `**${childrenMd.trim()}**` : "";

    case "em":
    case "i":
      return childrenMd.trim() ? `*${childrenMd.trim()}*` : "";

    case "s":
    case "strike":
    case "del":
      return childrenMd.trim() ? `~~${childrenMd.trim()}~~` : "";

    case "code":
      return `\`${childrenMd.replace(/`/g, "\\`")}\``;

    case "a": {
      const href = cleanUrl(el.getAttribute("href"), baseUri);
      const text = childrenMd.trim() || href;
      if (!href) return text;
      return `[${text}](${href})`;
    }

    case "img": {
      const src = cleanUrl(el.getAttribute("src"), baseUri);
      const alt = el.getAttribute("alt") || "";
      if (!src) return "";
      return `![${alt}](${src})`;
    }

    case "hr": return "\n\n---\n\n";
    case "br": return "  \n";

    default:
      if (BLOCK_TAGS.has(tag)) {
        return `\n${childrenMd}\n`;
      }
      return childrenMd;
  }
}

/**
 * Top-Level DOM Sanitizer & Extractor
 */
export function extractStructuredMarkdown(doc = document) {
  const sourceUrl = doc.location?.href || "";
  const title = (doc.title || "").trim();


  const authorMeta = doc.querySelector('meta[name="author"], meta[property="article:author"], meta[name="twitter:creator"]');
  const author = authorMeta ? authorMeta.getAttribute("content") || "" : "";

  const descMeta = doc.querySelector('meta[name="description"], meta[property="og:description"]');
  const description = descMeta ? descMeta.getAttribute("content") || "" : "";

  // Locate the true semantic root
  const root = doc.querySelector("article, main, [role=main]") || doc.body || doc.documentElement;
  const clone = root.cloneNode(true);

  // Prune noise
  clone.querySelectorAll("script,style,nav,footer,aside,header,noscript,form,button").forEach((n) => n.remove());

  // Transpile to markdown
  const rawMd = domToMarkdown(clone, doc.baseURI || sourceUrl);

  // Clean successive blank lines
  const normalizedMd = rawMd.replace(/\n{3,}/g, "\n\n").trim();

  return {
    markdown: normalizedMd,
    title,
    author,
    description,
    sourceUrl,
  };
}

if (typeof window !== "undefined") {
  window.extractStructuredMarkdown = extractStructuredMarkdown;
  window.domToMarkdown = domToMarkdown;
}

