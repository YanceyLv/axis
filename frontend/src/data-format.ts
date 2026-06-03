export function formatPrice(value: number): string {
  const absoluteValue = Math.abs(value);
  if (absoluteValue < 0.001) return value.toFixed(8);
  if (absoluteValue < 1) return value.toFixed(4);
  return value.toFixed(3);
}

export function formatPercent(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function dateParts(value: string): Record<string, string> | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  });
  return Object.fromEntries(formatter.formatToParts(date).map((part) => [part.type, part.value]));
}

export function formatDateTime(value: string | null | undefined, fallback = "暂无"): string {
  if (!value) return fallback;
  const parts = dateParts(value);
  if (!parts) return value;
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`;
}

export function formatDateMinute(value: string | null | undefined, fallback = "暂无"): string {
  if (!value) return fallback;
  const parts = dateParts(value);
  if (!parts) return value;
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}

export function formatTimeOnly(value: string | null | undefined, fallback = "暂无"): string {
  if (!value) return fallback;
  const parts = dateParts(value);
  if (!parts) return value;
  return `${parts.hour}:${parts.minute}`;
}
