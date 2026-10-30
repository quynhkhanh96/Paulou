// Browser smoke test: real Chromium with a fake microphone, the built frontend
// (vite preview) and the real FastAPI app with a STUB pipeline
// (tests/api/e2e_app.py). It proves the wiring that unit tests cannot: the
// browser's own MediaRecorder output is accepted by the backend, and clips play.
//
//   PAULOU_CHROMIUM=/path/to/chromium PAULOU_URL=http://localhost:4173 node e2e/smoke.mjs
import { chromium } from "playwright-core";

const url = process.env.PAULOU_URL ?? "http://localhost:4173";
const shots = process.env.PAULOU_SHOTS ?? "";
const browser = await chromium.launch({
  executablePath: process.env.PAULOU_CHROMIUM,
  args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--no-sandbox", "--autoplay-policy=no-user-gesture-required"],
});
const context = await browser.newContext({ permissions: ["microphone"], viewport: { width: 900, height: 1000 } });
const page = await context.newPage();
const failures = [];
const audioResponses = [];
page.on("response", (r) => {
  if (r.url().includes("/audio")) audioResponses.push(`${r.status()} ${r.headers()["content-type"]}`);
});
page.on("pageerror", (e) => failures.push(`pageerror: ${e.message}`));
page.on("console", (m) => m.type() === "error" && failures.push(`console: ${m.text()}`));

const step = async (name, fn) => {
  try {
    await fn();
    console.log("ok   ", name);
  } catch (e) {
    failures.push(`${name}: ${e.message.split("\n")[0]}`);
    console.log("FAIL ", name, e.message.split("\n")[0]);
  }
};
const shot = async (name) => shots && (await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true }));

await page.goto(url);
await step("form is shown", async () => {
  await page.getByLabel(/which sentence/i).waitFor();
  await shot("1-input");
});
await step("prepare a sentence", async () => {
  await page.getByLabel(/which sentence/i).fill("Bonjour les petits amis");
  await page.getByRole("button", { name: /prepare/i }).click();
  await page.getByRole("tab", { name: "petits amis" }).waitFor({ timeout: 15000 });
  await shot("2-practice");
});
await step("model becomes ready and recording unlocks", async () => {
  await page.getByRole("button", { name: /record this chunk/i }).waitFor();
  await page.waitForFunction(() => !document.querySelector("button.btn-primary")?.disabled, null, { timeout: 15000 });
});
await step("listening plays a real clip", async () => {
  await page.getByRole("button", { name: "Listen", exact: true }).click();
  await page.waitForTimeout(800);
  if (!audioResponses.some((r) => r.startsWith("200 audio/mpeg"))) throw new Error(`no 200 audio/mpeg (${audioResponses})`);
});
await step("record with the real MediaRecorder, send, see the result", async () => {
  await page.getByRole("tab", { name: "petits amis" }).click();
  await page.getByRole("button", { name: /record this chunk/i }).click();
  await page.getByRole("button", { name: /stop and check/i }).waitFor();
  await page.waitForTimeout(1500);
  await page.getByRole("button", { name: /stop and check/i }).click();
  await page.getByRole("list", { name: /sound by sound/i }).first().waitFor({ timeout: 15000 });
  await shot("3-result");
  const kinds = await page.locator(".track .tk").evaluateAll((els) => els.map((e) => e.className.split(" ")[1]));
  if (!kinds.includes("tk-D") || !kinds.includes("tk-M")) throw new Error(`unexpected ops: ${kinds}`);
  const score = await page.locator(".score").innerText();
  if (!/words correct/.test(score) || !/sounds correct/.test(score)) throw new Error(`score line: ${score}`);
  const boxes = await page.locator(".results > .cols h3").allInnerTexts();
  if (boxes[0] !== "Needs fixing") throw new Error(`boxes: ${boxes}`);
});
await step("a word chip opens its card, the clips play", async () => {
  const chip = page.locator("button.wchip").first();
  await chip.waitFor();
  if ((await chip.getAttribute("aria-expanded")) !== "true") await chip.click();
  const card = page.getByRole("region", { name: /^Details:/ });
  await card.waitFor();
  const before = audioResponses.length;
  await card.getByRole("button", { name: /hear the model/i }).click();
  await page.waitForTimeout(800);
  if (audioResponses.length <= before || !audioResponses.at(-1).startsWith("200 audio/mpeg")) throw new Error("model clip did not load");
  await card.getByRole("button", { name: /hear yourself/i }).click();
  await page.waitForTimeout(600);
  const label = await card.getByRole("button", { name: /hear yourself|loading|could not play/i }).innerText();
  if (/could not play/i.test(label)) throw new Error(`own clip: ${label}`);
  await shot("3b-card");
});
await step("drill one unit", async () => {
  await page.locator("button.unit", { hasText: "petits" }).click();
  await page.getByRole("button", { name: /record "petits"/i }).click();
  await page.waitForTimeout(1200);
  await page.getByRole("button", { name: /stop and check/i }).click();
  await page.getByRole("list", { name: /sound by sound/i }).first().waitFor({ timeout: 15000 });
});

await step("practise the whole sentence", async () => {
  await page.getByRole("tab", { name: "Whole sentence" }).click();
  await page.getByRole("button", { name: /record the whole sentence/i }).click();
  await page.waitForTimeout(1500);
  await page.getByRole("button", { name: /stop and check/i }).click();
  await page.getByRole("list", { name: /sound by sound/i }).first().waitFor({ timeout: 15000 });
  const groups = await page.getByRole("group", { name: /^Chunk \d/ }).count();
  if (groups < 2) throw new Error(`expected results grouped by chunk, got ${groups} groups`);
  await shot("4-whole-sentence");
});
await step("pronunciation guide opens and practice is kept", async () => {
  await page.getByRole("tab", { name: "Pronunciation guide" }).click();
  await page.getByRole("heading", { name: "Nasal vowels" }).waitFor();
  const before = audioResponses.length;
  await page.getByRole("button", { name: 'Listen to "si"' }).click();
  await page.waitForTimeout(800);
  if (audioResponses.length <= before || !audioResponses.at(-1).startsWith("200 audio/mpeg")) {
    throw new Error(`guide example did not play (${audioResponses.slice(before)})`);
  }
  await page.getByRole("heading", { name: "/i/" }).scrollIntoViewIfNeeded();
  await shot("5-guide");
  await page.getByRole("tab", { name: "Practice" }).click();
  await page.getByRole("list", { name: /sound by sound/i }).first().waitFor();
});

await browser.close();
if (failures.length) {
  console.error("\nFAILURES:\n" + failures.join("\n"));
  process.exit(1);
}
console.log("\nsmoke test passed");
