import { realpathSync } from "node:fs";
import { createRequire } from "node:module";

// conda-forge's commitlint keeps the conventional rules inside its own package, where a project can't
// find them by name. Resolve them from commitlint itself (argv[1] is its command).
const conventional = createRequire(realpathSync(process.argv[1])).resolve("@commitlint/config-conventional");

/** @type {import('@commitlint/types').UserConfig} */
export default {
  extends: [conventional],
  rules: {
    // Bodies are written as unwrapped paragraphs.
    "body-max-line-length": [0],
    "footer-max-line-length": [0],
  },
};
