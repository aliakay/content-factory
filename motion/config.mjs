// Paths for the node helpers. factory/config.py exports CF_* to child processes; these defaults cover running by hand.
import { existsSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";

const home = os.homedir();
const pick = (env, ...paths) => process.env[env] || paths.find((p) => existsSync(p));

export default {
  root: process.env.CF_ROOT || path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."),
  ffmpeg: pick("CF_FFMPEG", `${home}/opt/bin/ffmpeg`) || "ffmpeg",
  // Chromium runtime libs unpacked without root; empty when the system has them
  chromeLibs: process.env.CF_CHROME_LIBS ?? [`${home}/opt/chromelibs/root/usr/lib/x86_64-linux-gnu`,
    `${home}/opt/chromelibs/root/usr/lib/x86_64-linux-gnu/gbm`].filter((p) => existsSync(p)).join(":"),
};
