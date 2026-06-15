import { readdir, readFile, writeFile, stat } from "node:fs/promises";
import { join } from "node:path";
import JavaScriptObfuscator from "javascript-obfuscator";

const ROOT = ".next/static/chunks";

const OPTIONS = {
  compact: true,
  controlFlowFlattening: false,
  deadCodeInjection: false,
  selfDefending: false,
  simplify: true,
  stringArray: true,
  stringArrayThreshold: 0.6,
  stringArrayEncoding: ["base64"],
  identifierNamesGenerator: "mangled",
  numbersToExpressions: false,
};

async function* jsFiles(dir) {
  for (const entry of await readdir(dir)) {
    const full = join(dir, entry);
    const info = await stat(full);
    if (info.isDirectory()) {
      yield* jsFiles(full);
    } else if (entry.endsWith(".js")) {
      yield full;
    }
  }
}

let count = 0;
for await (const file of jsFiles(ROOT)) {
  const code = await readFile(file, "utf8");
  const out = JavaScriptObfuscator.obfuscate(code, OPTIONS).getObfuscatedCode();
  await writeFile(file, out);
  count += 1;
}
console.log(`obfuscated ${count} chunk(s)`);
