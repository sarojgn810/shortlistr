/**
 * Copy the VAD runtime out of node_modules into public/vad.
 *
 * @ricky0123/vad-web loads its ONNX model and the onnxruntime wasm from a CDN
 * by default. In a local-first app that would mean the browser reaches an
 * outside host in order to hear you — so the assets are served from our own
 * origin instead.
 *
 * This runs on postinstall rather than being committed: the files are ~40MB of
 * build output that already lives in node_modules, and vendoring them into git
 * would bloat every clone to avoid a copy that takes a second.
 */

import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "public", "vad");

const ASSETS = [
  ["@ricky0123/vad-web/dist/silero_vad_v5.onnx", "silero_vad_v5.onnx"],
  ["@ricky0123/vad-web/dist/silero_vad_legacy.onnx", "silero_vad_legacy.onnx"],
  ["@ricky0123/vad-web/dist/vad.worklet.bundle.min.js", "vad.worklet.bundle.min.js"],
  ["onnxruntime-web/dist/ort-wasm-simd-threaded.wasm", "ort-wasm-simd-threaded.wasm"],
  ["onnxruntime-web/dist/ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.mjs"],
  ["onnxruntime-web/dist/ort-wasm-simd-threaded.jsep.wasm", "ort-wasm-simd-threaded.jsep.wasm"],
  ["onnxruntime-web/dist/ort-wasm-simd-threaded.jsep.mjs", "ort-wasm-simd-threaded.jsep.mjs"],
];

mkdirSync(out, { recursive: true });

let copied = 0;
let missing = 0;
for (const [from, to] of ASSETS) {
  const src = join(root, "node_modules", from);
  if (!existsSync(src)) {
    // A missing asset must not fail the install — voice is one feature, and
    // npm install is how the whole dashboard comes up.
    console.warn(`[vendor-vad] not found, skipping: ${from}`);
    missing++;
    continue;
  }
  copyFileSync(src, join(out, to));
  copied++;
}

console.log(`[vendor-vad] ${copied} asset(s) in public/vad${missing ? `, ${missing} missing` : ""}`);
