/**
 * Reports as real PDF files, made in the browser with no library: each A4 page is laid out on a
 * canvas (so Urdu / Arabic script is shaped by the browser's own text engine, which PDF fonts
 * would need a shaping library for) and the pages are written into a small PDF as JPEG images.
 *
 *   const r = new ReportBuilder("Route report", "From A to B");
 *   r.heading("Summary"); r.keyValues([["Distance", "13.3 km"]]); r.image(canvas);
 *   const blob = await r.toPdf();
 */
const PAGE_W = 1240; // A4 at 150 dpi
const PAGE_H = 1754;
const M = 90; // margin
const FOOT = 70;
const BRAND = "#0f5a39";
const INK = "#1b2621";
const MUTE = "#5c6b64";
const RTL = /[֐-ࣿיִ-﷿ﹰ-﻿]/;
const LATIN = '"Plus Jakarta Sans", system-ui, sans-serif';
const URDU = '"Noto Nastaliq Urdu", "Noto Naskh Arabic", "Segoe UI", sans-serif';

/** Make sure the web fonts are ready before drawing (else canvas uses a fallback). */
async function fontsReady() {
  try {
    await Promise.all([document.fonts.load(`400 24px "Plus Jakarta Sans"`), document.fonts.load(`700 24px "Plus Jakarta Sans"`), document.fonts.load(`400 24px "Noto Nastaliq Urdu"`, "اردو")]);
  } catch {
    /* draw with fallbacks */
  }
}

export class ReportBuilder {
  private pages: HTMLCanvasElement[] = [];
  private ctx!: CanvasRenderingContext2D;
  private y = 0;
  private ready: Promise<void>;
  private ops: (() => void | Promise<void>)[] = [];

  constructor(
    private title: string,
    private subtitle = "",
  ) {
    this.ready = fontsReady();
  }

  // ---------------------------------------------------------------- queued content
  heading(text: string) {
    this.ops.push(() => {
      this.need(80);
      this.y += 18;
      this.text(text, { size: 30, weight: 700, color: BRAND });
      this.ctx.fillStyle = "#d9c27a";
      this.ctx.fillRect(M, this.y + 2, 80, 4);
      this.y += 22;
    });
    return this;
  }
  paragraph(text: string, opts: { size?: number; color?: string } = {}) {
    this.ops.push(() => {
      for (const para of text.split(/\n{2,}/)) {
        this.text(para.replace(/\s*\n\s*/g, " "), { size: opts.size ?? 22, color: opts.color ?? INK });
        this.y += 10;
      }
    });
    return this;
  }
  bullets(items: string[]) {
    this.ops.push(() => {
      for (const it of items) this.text(`•  ${it}`, { size: 21, color: INK, indent: 8 });
      this.y += 6;
    });
    return this;
  }
  keyValues(rows: [string, string][]) {
    this.ops.push(() => {
      const kw = 330;
      for (const [k, v] of rows) {
        if (!v) continue;
        const lines = this.wrap(v, PAGE_W - 2 * M - kw - 20, 21, 400);
        const h = Math.max(1, lines.length) * this.lineH(21, v) + 14;
        this.need(h);
        this.ctx.fillStyle = "#f3f7f4";
        this.ctx.fillRect(M, this.y, PAGE_W - 2 * M, h - 4);
        this.draw(k, M + 14, this.y + 8, { size: 19, weight: 700, color: MUTE, maxW: kw - 20 });
        let yy = this.y + 8;
        for (const l of lines) {
          this.draw(l, M + kw, yy, { size: 21, color: INK, maxW: PAGE_W - 2 * M - kw - 20 });
          yy += this.lineH(21, l);
        }
        this.y += h;
      }
      this.y += 8;
    });
    return this;
  }
  table(headers: string[], rows: string[][], widths?: number[]) {
    this.ops.push(() => {
      const full = PAGE_W - 2 * M;
      const ws = widths ?? headers.map(() => 1 / headers.length);
      const cols = ws.map((w) => w * full);
      const row = (cells: string[], head: boolean) => {
        const wrapped = cells.map((c, i) => this.wrap(c ?? "", cols[i]! - 16, 19, head ? 700 : 400));
        const h = Math.max(...wrapped.map((w, i) => Math.max(1, w.length) * this.lineH(19, cells[i] ?? ""))) + 14;
        if (this.need(h) && !head) row(headers, true);
        if (head) {
          this.ctx.fillStyle = BRAND;
          this.ctx.fillRect(M, this.y, full, h);
        }
        let x = M;
        wrapped.forEach((lines, i) => {
          let yy = this.y + 7;
          for (const l of lines) {
            this.draw(l, x + 8, yy, { size: 19, weight: head ? 700 : 400, color: head ? "#fff" : INK, maxW: cols[i]! - 16 });
            yy += this.lineH(19, l);
          }
          x += cols[i]!;
        });
        this.ctx.fillStyle = "#e3ebe6";
        this.ctx.fillRect(M, this.y + h - 1, full, 1);
        this.y += h;
      };
      row(headers, true);
      for (const r of rows) row(r, false);
      this.y += 12;
    });
    return this;
  }
  /** A picture (a map, a photo); scaled to the text width, `maxH` px tall at most. */
  image(src: CanvasImageSource & { width: number; height: number }, caption?: string, maxH = 980) {
    this.ops.push(() => {
      const full = PAGE_W - 2 * M;
      let w = full;
      let h = (src.height / src.width) * w;
      if (h > maxH) {
        h = maxH;
        w = (src.width / src.height) * h;
      }
      this.need(h + (caption ? 40 : 10));
      const x = M + (full - w) / 2;
      this.ctx.drawImage(src, x, this.y, w, h);
      this.ctx.strokeStyle = "#d5dfda";
      this.ctx.lineWidth = 2;
      this.ctx.strokeRect(x, this.y, w, h);
      this.y += h + 8;
      if (caption) this.text(caption, { size: 17, color: MUTE });
      this.y += 10;
    });
    return this;
  }
  spacer(px = 20) {
    this.ops.push(() => {
      this.y += px;
    });
    return this;
  }
  pageBreak() {
    this.ops.push(() => this.newPage());
    return this;
  }

  // ---------------------------------------------------------------- output
  async render(): Promise<HTMLCanvasElement[]> {
    if (this.pages.length) return this.pages;
    await this.ready;
    this.newPage(true);
    for (const op of this.ops) await op();
    this.pages.forEach((p, i) => this.footer(p, i + 1, this.pages.length));
    return this.pages;
  }

  async toPdf(): Promise<Blob> {
    const pages = await this.render();
    const jpegs = await Promise.all(pages.map((c) => canvasJpeg(c, 0.86)));
    return writePdf(jpegs.map((data) => ({ data, w: PAGE_W, h: PAGE_H })), this.title);
  }

  // ---------------------------------------------------------------- layout
  private newPage(first = false) {
    const c = document.createElement("canvas");
    c.width = PAGE_W;
    c.height = PAGE_H;
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, PAGE_W, PAGE_H);
    this.pages.push(c);
    this.ctx = ctx;
    // Header band
    ctx.fillStyle = BRAND;
    ctx.fillRect(0, 0, PAGE_W, first ? 210 : 70);
    ctx.fillStyle = "#c99a22";
    ctx.fillRect(0, first ? 210 : 70, PAGE_W, 6);
    if (first) {
      this.draw("WATAN-E-PAK · AI REAL ESTATE PORTAL", M, 34, { size: 18, weight: 700, color: "#e7d18f" });
      this.y = 66;
      this.text(this.title, { size: 44, weight: 700, color: "#ffffff" });
      if (this.subtitle) this.text(this.subtitle, { size: 22, color: "#d7ece0" });
      this.y = 250;
    } else {
      this.draw(this.title, M, 20, { size: 22, weight: 700, color: "#ffffff", maxW: PAGE_W - 2 * M });
      this.y = 110;
    }
  }
  private footer(c: HTMLCanvasElement, n: number, of: number) {
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#e3ebe6";
    ctx.fillRect(M, PAGE_H - FOOT, PAGE_W - 2 * M, 1);
    ctx.fillStyle = MUTE;
    ctx.font = `400 16px ${LATIN}`;
    ctx.textBaseline = "top";
    ctx.textAlign = "left";
    ctx.direction = "ltr";
    ctx.fillText(`Generated by Watan-e-Pak AI · ${new Date().toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })} · ${window.location.host}`, M, PAGE_H - FOOT + 16);
    ctx.textAlign = "right";
    ctx.fillText(`Page ${n} of ${of}`, PAGE_W - M, PAGE_H - FOOT + 16);
  }
  /** Start a new page when `h` px don't fit. True when it did. */
  private need(h: number): boolean {
    if (this.y + h <= PAGE_H - FOOT - 20) return false;
    this.newPage();
    return true;
  }
  private font(size: number, weight: number, sample: string) {
    return RTL.test(sample) ? `${weight} ${Math.round(size * 0.92)}px ${URDU}` : `${weight} ${size}px ${LATIN}`;
  }
  private lineH(size: number, sample: string) {
    return RTL.test(sample) ? size * 2.1 : size * 1.45;
  }
  private wrap(text: string, maxW: number, size: number, weight: number): string[] {
    this.ctx.font = this.font(size, weight, text);
    const out: string[] = [];
    for (const raw of String(text).split("\n")) {
      const words = raw.split(/\s+/).filter(Boolean);
      let line = "";
      for (const w of words) {
        const t = line ? `${line} ${w}` : w;
        if (this.ctx.measureText(t).width <= maxW || !line) line = t;
        else {
          out.push(line);
          line = w;
        }
      }
      out.push(line);
    }
    return out;
  }
  private draw(text: string, x: number, y: number, o: { size: number; weight?: number; color: string; maxW?: number }) {
    const ctx = this.ctx;
    const rtl = RTL.test(text);
    ctx.font = this.font(o.size, o.weight ?? 400, text);
    ctx.fillStyle = o.color;
    ctx.textBaseline = "top";
    ctx.direction = rtl ? "rtl" : "ltr";
    ctx.textAlign = rtl ? "right" : "left";
    const rx = rtl ? (o.maxW ? x + o.maxW : PAGE_W - M) : x;
    ctx.fillText(text, rx, y + (rtl ? o.size * 0.35 : 0), o.maxW);
  }
  private text(text: string, o: { size: number; weight?: number; color: string; indent?: number }) {
    const lines = this.wrap(text, PAGE_W - 2 * M - (o.indent ?? 0), o.size, o.weight ?? 400);
    for (const l of lines) {
      const h = this.lineH(o.size, l);
      this.need(h);
      this.draw(l, M + (o.indent ?? 0), this.y, o);
      this.y += h;
    }
  }
}

async function canvasJpeg(c: HTMLCanvasElement, q: number): Promise<Uint8Array> {
  const blob = await new Promise<Blob>((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("canvas export failed"))), "image/jpeg", q));
  return new Uint8Array(await blob.arrayBuffer());
}

/** A canvas as a PNG file. */
export function canvasPng(c: HTMLCanvasElement): Promise<Blob> {
  return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("canvas export failed"))), "image/png"));
}

/** A minimal PDF: one full-page JPEG per page, A4. */
function writePdf(pages: { data: Uint8Array; w: number; h: number }[], title: string): Blob {
  const enc = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const offsets: number[] = [];
  let len = 0;
  const put = (x: string | Uint8Array) => {
    const b = typeof x === "string" ? enc.encode(x) : x;
    chunks.push(b);
    len += b.length;
  };
  const obj = (n: number, body: (string | Uint8Array)[]) => {
    offsets[n] = len;
    put(`${n} 0 obj\n`);
    body.forEach(put);
    put("\nendobj\n");
  };
  const pdfStr = (s: string) => `(${s.replace(/[\\()]/g, (m) => `\\${m}`).replace(/[^\x20-\x7e]/g, "?")})`;
  const PW = 595.28;
  const PH = 841.89;
  put("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n");
  // 1 catalog, 2 pages, 3 info, then per page: page, content, image
  const kids = pages.map((_, i) => `${4 + i * 3} 0 R`).join(" ");
  obj(1, ["<< /Type /Catalog /Pages 2 0 R >>"]);
  obj(2, [`<< /Type /Pages /Kids [${kids}] /Count ${pages.length} >>`]);
  obj(3, [`<< /Title ${pdfStr(title)} /Producer (Watan-e-Pak AI) /CreationDate (D:${new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14)}) >>`]);
  pages.forEach((p, i) => {
    const n = 4 + i * 3;
    const content = `q ${PW} 0 0 ${PH} 0 0 cm /Im0 Do Q`;
    obj(n, [`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PW} ${PH}] /Resources << /XObject << /Im0 ${n + 2} 0 R >> >> /Contents ${n + 1} 0 R >>`]);
    obj(n + 1, [`<< /Length ${content.length} >>\nstream\n${content}\nendstream`]);
    obj(n + 2, [`<< /Type /XObject /Subtype /Image /Width ${p.w} /Height ${p.h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${p.data.length} >>\nstream\n`, p.data, "\nendstream"]);
  });
  const count = 4 + pages.length * 3;
  const xref = len;
  put(`xref\n0 ${count}\n0000000000 65535 f \n`);
  for (let n = 1; n < count; n++) put(`${String(offsets[n]).padStart(10, "0")} 00000 n \n`);
  put(`trailer\n<< /Size ${count} /Root 1 0 R /Info 3 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  return new Blob(chunks as BlobPart[], { type: "application/pdf" });
}
