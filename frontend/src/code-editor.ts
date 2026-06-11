export function extractStrategyErrorLine(message: string | null | undefined): number | null {
  if (!message) return null;

  const match = message.match(/第\s*(\d+)\s*行/i) ?? message.match(/\bline\s+(\d+)\b/i);
  if (!match) return null;

  const lineNumber = Number(match[1]);
  return Number.isInteger(lineNumber) && lineNumber > 0 ? lineNumber : null;
}

export function splitCodeLines(code: string): string[] {
  const lines = code.split("\n");
  return lines.length ? lines : [""];
}
