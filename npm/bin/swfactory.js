#!/usr/bin/env node
"use strict";
// Runs the swfactory CLI (a Python package) through uv, pinned to this package's version.
// uv downloads Python and the package the first time and reuses its cache afterwards.
const { spawnSync } = require("node:child_process");
const { version } = require("../package.json");

const source = process.env.SWFACTORY_FROM || `swfactory==${version}`;
const args = ["--from", source, "swfactory", ...process.argv.slice(2)];

function run(command, commandArgs) {
  return spawnSync(command, commandArgs, { stdio: "inherit" });
}

let result = run("uvx", args);
if (result.error && result.error.code === "ENOENT") {
  result = run("uv", ["tool", "run", ...args]);
}
if (result.error && result.error.code === "ENOENT") {
  console.error(
    "swfactory needs uv (https://docs.astral.sh/uv/). Install it with:\n" +
      "  curl -LsSf https://astral.sh/uv/install.sh | sh\n" +
      "then run this command again."
  );
  process.exit(127);
}
if (result.error) {
  console.error(`swfactory: ${result.error.message}`);
  process.exit(1);
}
if (result.signal) {
  process.kill(process.pid, result.signal);
}
process.exit(result.status === null ? 1 : result.status);
