import type { Candle } from "../types";

export function SparkLine({ values }: { values: number[] }) {
  if (values.length === 0) {
    return <div className="chart-empty">暂无数据</div>;
  }

  const width = 160;
  const height = 48;
  const padding = 4;
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const range = max - min || 1;
  const points = values
    .map((value, index) => {
      const x =
        values.length === 1
          ? width / 2
          : padding + (index / (values.length - 1)) * (width - padding * 2);
      const y = height - padding - ((value - min) / range) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(" ");
  const areaPoints = `${padding},${height - padding} ${points} ${width - padding},${height - padding}`;

  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="趋势迷你图">
      <polygon className="sparkline-area" points={areaPoints} />
      <polyline points={points} />
      {points.split(" ").map((point, index) => {
        const [cx, cy] = point.split(",");
        return <circle className="sparkline-dot" key={`${point}-${index}`} cx={cx} cy={cy} r="2.2" />;
      })}
    </svg>
  );
}

export function KlineChart({ candles, signalTime }: { candles: Candle[]; signalTime?: string | null }) {
  const visibleCandles = selectVisibleCandles(candles, signalTime).filter((candle) =>
    [candle.open, candle.high, candle.low, candle.close, candle.volume].every(Number.isFinite)
  );

  if (visibleCandles.length === 0) {
    return <div className="chart-empty">暂无 K 线数据</div>;
  }

  const width = 720;
  const height = 280;
  const chartHeight = 210;
  const volumeTop = 224;
  const paddingX = 24;
  const bodyWidth = Math.max(3, Math.min(8, (width - paddingX * 2) / Math.max(visibleCandles.length, 1) * 0.58));
  const lows = visibleCandles.map((candle) => candle.low);
  const highs = visibleCandles.map((candle) => candle.high);
  const volumes = visibleCandles.map((candle) => candle.volume);
  const rawMinPrice = Math.min(...lows);
  const rawMaxPrice = Math.max(...highs);
  const rawRange = rawMaxPrice - rawMinPrice || Math.max(rawMaxPrice * 0.02, 1);
  const minPrice = rawMinPrice - rawRange * 0.08;
  const maxPrice = rawMaxPrice + rawRange * 0.08;
  const priceRange = maxPrice - minPrice || 1;
  const maxVolume = Math.max(...volumes, 1);
  const signalIndex = signalTime ? findSignalCandleIndex(visibleCandles, signalTime) : -1;

  const xForIndex = (index: number) =>
    visibleCandles.length === 1
      ? width / 2
      : paddingX + (index / (visibleCandles.length - 1)) * (width - paddingX * 2);
  const yForPrice = (price: number) =>
    16 + (1 - (price - minPrice) / priceRange) * (chartHeight - 24);

  return (
    <svg className="kline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="K线图">
      {[0, 1, 2, 3].map((line) => (
        <line
          className="kline-grid"
          key={line}
          x1="16"
          x2={width - 16}
          y1={24 + line * 52}
          y2={24 + line * 52}
        />
      ))}

      {visibleCandles.map((candle, index) => {
        const x = xForIndex(index);
        const openY = yForPrice(candle.open);
        const closeY = yForPrice(candle.close);
        const highY = yForPrice(candle.high);
        const lowY = yForPrice(candle.low);
        const isUp = candle.close >= candle.open;
        const bodyY = Math.min(openY, closeY);
        const bodyHeight = Math.max(2, Math.abs(closeY - openY));
        const volumeHeight = (candle.volume / maxVolume) * 42;

        return (
          <g className={isUp ? "candle up" : "candle down"} key={`${candle.time}-${index}`}>
            <line className="wick" x1={x} x2={x} y1={highY} y2={lowY} />
            <rect
              className="body"
              x={x - bodyWidth / 2}
              y={bodyY}
              width={bodyWidth}
              height={bodyHeight}
              rx="2"
            />
            <rect
              className="volume"
              x={x - bodyWidth / 2}
              y={volumeTop + 42 - volumeHeight}
              width={bodyWidth}
              height={volumeHeight}
              rx="1"
            />
          </g>
        );
      })}
      {signalIndex >= 0 ? <SignalMarker x={xForIndex(signalIndex)} y={yForPrice(visibleCandles[signalIndex].high)} /> : null}
    </svg>
  );
}

function selectVisibleCandles(candles: Candle[], signalTime?: string | null): Candle[] {
  const windowSize = 120;
  if (!signalTime || candles.length <= windowSize) return candles.slice(-windowSize);

  const fullIndex = findSignalCandleIndex(candles, signalTime);
  if (fullIndex < 0) return candles.slice(-windowSize);

  const start = Math.max(0, Math.min(fullIndex - Math.floor(windowSize * 0.72), candles.length - windowSize));
  return candles.slice(start, start + windowSize);
}

function findSignalCandleIndex(candles: Candle[], signalTime: string): number {
  const target = new Date(signalTime).getTime();
  if (Number.isNaN(target) || candles.length === 0) return -1;

  let bestIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  candles.forEach((candle, index) => {
    const value = new Date(candle.time).getTime();
    if (Number.isNaN(value)) return;
    const distance = Math.abs(value - target);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
}

function SignalMarker({ x, y }: { x: number; y: number }) {
  const markerY = Math.max(12, y - 14);
  return (
    <g className="signal-marker" transform={`translate(${x}, ${markerY})`}>
      <path d="M0 -10 L8 6 L0 2 L-8 6 Z" />
      <circle r="3" />
    </g>
  );
}
