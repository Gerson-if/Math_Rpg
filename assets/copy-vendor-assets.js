#!/usr/bin/env node
/**
 * Copies the third-party static assets the app used to pull from a CDN
 * (Tailwind is handled separately by the Tailwind CLI build, see
 * package.json's "build:css") into app/static/vendor, so production never
 * makes a request to fonts.googleapis.com, cdnjs.cloudflare.com,
 * unpkg.com, or any other CDN at runtime.
 *
 * Run via `npm run build` (or `npm run copy:vendor` alone). Safe to run
 * repeatedly — it always overwrites app/static/vendor with whatever is
 * currently in node_modules, so it stays in sync after a `npm update`.
 *
 * app/static/vendor is git-ignored (see .gitignore) — it's build output,
 * not source, same as app/static/css/tailwind.css. That's exactly why
 * this step has to run as part of every install/update, not just once by
 * hand: a fresh `git clone` has no vendor/ directory at all until this
 * runs.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const NODE_MODULES = path.join(ROOT, "node_modules");
const VENDOR_DIR = path.join(ROOT, "app", "static", "vendor");

function rmrf(target) {
  fs.rmSync(target, { recursive: true, force: true });
}

function copyFile(src, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDir(srcPath, destPath);
    } else {
      copyFile(srcPath, destPath);
    }
  }
}

function requirePkgDir(pkgName) {
  const dir = path.join(NODE_MODULES, pkgName);
  if (!fs.existsSync(dir)) {
    throw new Error(
      `${pkgName} not found in node_modules — run "npm install" first.`
    );
  }
  return dir;
}

function main() {
  rmrf(VENDOR_DIR);

  // htmx — single UMD file, used as a plain <script src> just like the
  // unpkg.com CDN version was.
  {
    const pkg = requirePkgDir("htmx.org");
    copyFile(
      path.join(pkg, "dist", "htmx.min.js"),
      path.join(VENDOR_DIR, "htmx", "htmx.min.js")
    );
  }

  // FontAwesome Free — only the "all" bundle (solid/regular/brands) plus
  // its webfonts, same subset the CDN <link> was pulling in.
  {
    const pkg = requirePkgDir("@fortawesome/fontawesome-free");
    copyFile(
      path.join(pkg, "css", "all.min.css"),
      path.join(VENDOR_DIR, "fontawesome", "css", "all.min.css")
    );
    copyDir(
      path.join(pkg, "webfonts"),
      path.join(VENDOR_DIR, "fontawesome", "webfonts")
    );
  }

  // Fonts — Fontsource ships the exact same font files Google Fonts was
  // serving, packaged as plain @font-face CSS + woff2/woff files. Copying
  // each package's whole directory (not just the woff2 files) keeps the
  // css file's own `url(./files/...)` references pointing at the right
  // place without any path rewriting on our side.
  //
  // MedievalSharp: only ships weight 400 (index.css), matching what the
  // old Google Fonts request asked for. Cinzel: the old request was
  // "Cinzel:wght@400;600;800", so only those three weight-specific CSS
  // files are copied — not the whole package (which also has 500/700/900
  // we never used).
  {
    const medievalsharp = requirePkgDir("@fontsource/medievalsharp");
    const destDir = path.join(VENDOR_DIR, "fonts", "medievalsharp");
    copyFile(
      path.join(medievalsharp, "index.css"),
      path.join(destDir, "index.css")
    );
    copyDir(path.join(medievalsharp, "files"), path.join(destDir, "files"));
  }
  {
    const cinzel = requirePkgDir("@fontsource/cinzel");
    const destDir = path.join(VENDOR_DIR, "fonts", "cinzel");
    for (const cssFile of ["400.css", "600.css", "800.css"]) {
      copyFile(path.join(cinzel, cssFile), path.join(destDir, cssFile));
    }
    copyDir(path.join(cinzel, "files"), path.join(destDir, "files"));
  }

  console.log("Vendor assets copiados para app/static/vendor/.");
}

main();
