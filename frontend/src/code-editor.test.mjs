import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

function loadModule() {
  const source = fs.readFileSync(new URL("./code-editor.ts", import.meta.url), "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(output, { exports: module.exports, module }, { filename: "code-editor.ts" });
  return module.exports;
}

test("extractStrategyErrorLine finds backend Chinese line number", () => {
  const { extractStrategyErrorLine } = loadModule();
  assert.equal(extractStrategyErrorLine("策略代码无法执行：第 29 行：list indices must be integers"), 29);
});

test("extractStrategyErrorLine returns null when no line number exists", () => {
  const { extractStrategyErrorLine } = loadModule();
  assert.equal(extractStrategyErrorLine("保存策略失败"), null);
});

test("splitCodeLines keeps an empty editor renderable", () => {
  const { splitCodeLines } = loadModule();
  assert.deepEqual(Array.from(splitCodeLines("")), [""]);
  assert.deepEqual(Array.from(splitCodeLines("a\nb\n")), ["a", "b", ""]);
});
