#!/usr/bin/env node
/**
 * Neow CLI — Node.js launcher & isolated Python runtime bootstrapper.
 *
 * Allows installing and running Neow via `npm i -g neow-cli` or `npx neow-cli`.
 * Automatically provisions an isolated Python virtual environment in
 * `~/.neow/runtime-venv` on first run (or version upgrade) and forwards
 * full TTY stdio and signals to `neow.cli.main`.
 */

const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const PKG_ROOT = path.resolve(__dirname, "..");
const PKG_JSON = JSON.parse(
  fs.readFileSync(path.join(PKG_ROOT, "package.json"), "utf8")
);
const VERSION = PKG_JSON.version || "0.1.0";
const IS_WIN = process.platform === "win32";

function venvPythonPath(venvDir) {
  return IS_WIN
    ? path.join(venvDir, "Scripts", "python.exe")
    : path.join(venvDir, "bin", "python");
}

function findSystemPython() {
  const candidates = IS_WIN
    ? [
        ["python", []],
        ["py", ["-3"]],
        ["python3", []],
      ]
    : [
        ["python3", []],
        ["python", []],
      ];

  for (const [cmd, prefixArgs] of candidates) {
    const res = spawnSync(
      cmd,
      [
        ...prefixArgs,
        "-c",
        "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
      ],
      { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }
    );
    if (res.status === 0 && res.stdout) {
      const [maj, min] = res.stdout.trim().split(".").map(Number);
      if (maj > 3 || (maj === 3 && min >= 10)) {
        return { cmd, prefixArgs };
      }
    }
  }
  return null;
}

function hasUv() {
  const res = spawnSync("uv", ["--version"], {
    stdio: ["ignore", "ignore", "ignore"],
  });
  return res.status === 0;
}

function ensureRuntimePython() {
  // 1. Fast path: local repository `.venv` (for local development)
  const localVenvPy = venvPythonPath(path.join(PKG_ROOT, ".venv"));
  if (fs.existsSync(localVenvPy)) {
    return localVenvPy;
  }

  // 2. Managed runtime venv under ~/.neow/runtime-venv
  const neowHome = path.join(os.homedir(), ".neow");
  const runtimeVenv = path.join(neowHome, "runtime-venv");
  const runtimePy = venvPythonPath(runtimeVenv);
  const stampFile = path.join(runtimeVenv, ".neow-version");

  if (fs.existsSync(runtimePy) && fs.existsSync(stampFile)) {
    const installedVersion = fs.readFileSync(stampFile, "utf8").trim();
    if (installedVersion === VERSION) {
      return runtimePy;
    }
  }

  // 3. Bootstrap or upgrade ~/.neow/runtime-venv
  const sysPy = findSystemPython();
  if (!sysPy) {
    console.error(
      "\x1b[31m[neow] Error: Python >= 3.10 is required but was not found on PATH.\x1b[0m\n" +
        "Please install Python 3.10+ from https://www.python.org/downloads/ and try again."
    );
    process.exit(1);
  }

  fs.mkdirSync(neowHome, { recursive: true });
  console.error(
    `\x1b[36m◆ [neow] Initializing Python runtime environment (v${VERSION}) in ${runtimeVenv} ...\x1b[0m`
  );

  const useUv = hasUv();
  if (!fs.existsSync(runtimePy)) {
    const createRes = useUv
      ? spawnSync("uv", ["venv", runtimeVenv], { stdio: "inherit" })
      : spawnSync(
          sysPy.cmd,
          [...sysPy.prefixArgs, "-m", "venv", runtimeVenv],
          { stdio: "inherit" }
        );
    if (createRes.status !== 0) {
      console.error("\x1b[31m[neow] Failed to create Python virtual environment.\x1b[0m");
      process.exit(createRes.status || 1);
    }
  }

  const installRes = useUv
    ? spawnSync(
        "uv",
        ["pip", "install", "--python", runtimePy, "--upgrade", PKG_ROOT],
        { stdio: "inherit" }
      )
    : spawnSync(
        runtimePy,
        ["-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", PKG_ROOT],
        { stdio: "inherit" }
      );

  if (installRes.status !== 0) {
    console.error("\x1b[31m[neow] Failed to install Python dependencies.\x1b[0m");
    process.exit(installRes.status || 1);
  }

  fs.writeFileSync(stampFile, VERSION, "utf8");
  console.error("\x1b[32m◆ [neow] Runtime ready!\x1b[0m\n");
  return runtimePy;
}

function main() {
  const pythonExe = ensureRuntimePython();
  const args = ["-m", "neow.cli.main", ...process.argv.slice(2)];

  const child = spawn(pythonExe, args, {
    stdio: "inherit",
    env: {
      ...process.env,
      PYTHONUTF8: "1",
      PYTHONPATH: process.env.PYTHONPATH
        ? `${PKG_ROOT}${path.delimiter}${process.env.PYTHONPATH}`
        : PKG_ROOT,
    },
  });

  child.on("error", (err) => {
    console.error(`\x1b[31m[neow] Failed to launch Python process: ${err.message}\x1b[0m`);
    process.exit(1);
  });

  child.on("exit", (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
    } else {
      process.exit(code ?? 0);
    }
  });
}

main();
