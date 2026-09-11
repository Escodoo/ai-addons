// Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
// License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

function wrapTrimmed(prefix, suffix = prefix) {
    return (_node, inner) => (inner.trim() ? `${prefix}${inner.trim()}${suffix}` : "");
}

function blockTrimmed(prefix = "", suffix = "\n\n") {
    return (_node, inner) => `${prefix}${inner.trim()}${suffix}`;
}

function formatAnchor(node, inner) {
    const href = (node.getAttribute("href") || "").trim();
    const label = inner.trim() || href;
    if (href && /^(https?:|mailto:|\/)/i.test(href)) {
        return `[${label}](${href})`;
    }
    return label;
}

function formatListItem(node, inner) {
    const bullet = node.parentElement?.tagName === "OL" ? "1. " : "- ";
    return `${bullet}${inner.trim()}\n`;
}

function formatHeading(node, inner) {
    const level = Number(node.tagName[1]);
    return `${"#".repeat(level)} ${inner.trim()}\n\n`;
}

const TAG_FORMATTERS = {
    a: formatAnchor,
    b: wrapTrimmed("**"),
    blockquote: blockTrimmed("> "),
    code: wrapTrimmed("`"),
    div: blockTrimmed(),
    em: wrapTrimmed("*"),
    h1: formatHeading,
    h2: formatHeading,
    h3: formatHeading,
    h4: formatHeading,
    i: wrapTrimmed("*"),
    li: formatListItem,
    ol: blockTrimmed(),
    p: blockTrimmed(),
    pre: blockTrimmed("```\n", "\n```\n\n"),
    strong: wrapTrimmed("**"),
    table: blockTrimmed(),
    ul: blockTrimmed(),
};

function nodeToMarkdown(node) {
    if (node.nodeType === Node.TEXT_NODE) {
        return (node.nodeValue || "").replace(/\s+/g, " ");
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
        return "";
    }
    const tag = node.tagName.toLowerCase();
    if (tag === "br") {
        return "\n";
    }
    const inner = Array.from(node.childNodes)
        .map((child) => nodeToMarkdown(child))
        .join("");
    const formatter = TAG_FORMATTERS[tag];
    return formatter ? formatter(node, inner) : inner;
}

function formatTableRow(node) {
    const cellEls = Array.from(node.children).filter((child) =>
        ["TD", "TH"].includes(child.tagName)
    );
    const cells = cellEls.map((child) => nodeToMarkdown(child).trim());
    if (!cells.some(Boolean)) {
        return "";
    }
    const row = `| ${cells.join(" | ")} |`;
    const isHeader =
        cellEls.some((child) => child.tagName === "TH") ||
        node.parentElement?.tagName === "THEAD";
    if (isHeader) {
        return `${row}\n| ${cells.map(() => "---").join(" | ")} |\n`;
    }
    return `${row}\n`;
}

TAG_FORMATTERS.tr = formatTableRow;

export function htmlToMarkdown(html) {
    const container = document.createElement("div");
    container.innerHTML = html || "";
    return nodeToMarkdown(container)
        .replace(/\n{3,}/g, "\n\n")
        .trim();
}
