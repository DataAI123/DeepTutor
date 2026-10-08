import sharp from "sharp";
import { readFileSync, writeFileSync } from "fs";
import { fileURLToPath } from "url";
import path from "path";

const dir = path.dirname(fileURLToPath(import.meta.url));
const iconSvg = readFileSync(path.join(dir, "icon.svg"), "utf8");
const wordSvg = readFileSync(path.join(dir, "wordmark.svg"), "utf8");
const S = 6; // px per SVG unit in the master

const iconInk = await sharp(Buffer.from(iconSvg), { density: 72 * S })
  .png().extract({ left: 104 * S, top: 112 * S, width: 304 * S, height: 214 * S }).toBuffer();
const wordInk = await sharp(Buffer.from(wordSvg), { density: 72 * S })
  .png().extract({ left: 17 * S, top: 81 * S, width: 754 * S, height: 103 * S }).toBuffer();

async function build(iconRatio, gapU, padU, out) {
  const wh = 103 * S;
  const iconH = Math.round(wh * iconRatio);
  const ir = await sharp(iconInk).resize({ height: iconH }).png().toBuffer();
  const ii = await sharp(ir).metadata();
  const gap = gapU * S, pad = padU * S;
  const W = 2 * pad + gap + ii.width + gap + 754 * S + gap;
  const H = wh + 2 * pad;
  const buf = await sharp({ create: { width: W, height: H, channels: 4, background: { r: 0, g: 0, b: 0, alpha: 0 } } })
    .composite([
      { input: ir, left: pad + gap, top: Math.round((H - iconH) / 2) },
      { input: wordInk, left: pad + gap + ii.width + gap, top: pad },
    ])
    .png().toBuffer();
  const m = await sharp(buf).metadata();
  const ratio = m.width / m.height;
  console.log(`${out}: ${m.width}x${m.height} ratio=${ratio.toFixed(2)} | sidebar188px h=${(188 / ratio).toFixed(1)} textH=${((188 / ratio) * (103 / (103 + 2 * padU))).toFixed(1)} | mobile260px h=${(260 / ratio).toFixed(1)}`);
  if (out) writeFileSync(path.join(dir, out), buf);
  return { w: m.width, h: m.height };
}

await build(0.75, 10, 3, null);
await build(0.6, 8, 3, null);
await build(0.7, 8, 3, "banner-master.png");
