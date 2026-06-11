import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const appSource = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");

function extractLoadInitialDataBody(source) {
  const start = source.indexOf("const loadInitialData = useCallback(async () => {");
  assert.notEqual(start, -1, "loadInitialData callback should exist");

  const end = source.indexOf("\n  }, []);", start);
  assert.notEqual(end, -1, "loadInitialData callback should use an empty dependency array");

  return source.slice(start, end);
}

test("initial app load does not request heavy market pages", () => {
  const body = extractLoadInitialDataBody(appSource);

  assert.equal(body.includes("api.marketKlineStatus()"), false);
  assert.equal(body.includes("api.marketRadar()"), false);
});
