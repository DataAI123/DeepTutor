import sharp from "sharp";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import path from "path";

const dir = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(dir, "..", "public");

const icon = readFileSync(path.join(dir, "icon.svg"));
const black = readFileSync(path.join(dir, "icon-black.svg"));
const word = readFileSync(path.join(dir, "banner-master.png"));

async function gen(svg, file, w, h) {
  const img = sharp(svg, { density: 300 }).resize(w, h, { fit: "fill" });
  await img.png().toFile(`${out}/${file}`);
  console.log("wrote", file, `${w}x${h}`);
}

await gen(icon, "logo.png", 512, 512);
await gen(black, "logo_black.png", 512, 512);
await gen(word, "banner.png", 1294, 161);
await gen(icon, "favicon-32x32.png", 32, 32);
await gen(icon, "favicon-16x16.png", 16, 16);
await gen(icon, "apple-touch-icon.png", 180, 180);
