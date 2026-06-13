import { useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
  type UTCTimestamp
} from "lightweight-charts";
import { formatDateTime, formatPrice } from "../data-format";
import type { Candle } from "../types";

interface MarketKlineChartProps {
  candles: Candle[];
  signalTime?: string | null;
  loading?: boolean;
  chartHeaderExtra?: ReactNode;
}

interface HoverInfo {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export function MarketKlineChart({ candles, signalTime, loading = false, chartHeaderExtra }: MarketKlineChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markerRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const highPriceLineRef = useRef<IPriceLine | null>(null);
  const lowPriceLineRef = useRef<IPriceLine | null>(null);
  const [hoverInfo, setHoverInfo] = useState<HoverInfo | null>(null);

  const validCandles = useMemo(
    () => candles.filter((candle) => [candle.open, candle.high, candle.low, candle.close, candle.volume].every(Number.isFinite)),
    [candles]
  );
  const latestInfo = useMemo<HoverInfo | null>(() => {
    const latest = validCandles[validCandles.length - 1];
    if (!latest) return null;
    return {
      time: latest.time,
      open: latest.open,
      high: latest.high,
      low: latest.low,
      close: latest.close,
      volume: latest.volume
    };
  }, [validCandles]);
  const displayInfo = hoverInfo ?? latestInfo;
  const displayDirection = displayInfo ? (displayInfo.close >= displayInfo.open ? "up" : "down") : "flat";
  const dataRangeLabel = useMemo(() => {
    if (!validCandles.length) return "无数据";
    const first = validCandles[0];
    const last = validCandles[validCandles.length - 1];
    return `${formatDateTime(first.time)} - ${formatDateTime(last.time)}`;
  }, [validCandles]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      autoSize: true,
      height: 520,
      layout: {
        background: { type: ColorType.Solid, color: "#0b0e11" },
        textColor: "#9aa4b2",
        fontFamily: "'Inter', 'Segoe UI', sans-serif",
        fontSize: 12
      },
      grid: {
        vertLines: { color: "rgba(132, 142, 156, 0.12)" },
        horzLines: { color: "rgba(132, 142, 156, 0.12)" }
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "rgba(234, 236, 239, 0.45)",
          labelBackgroundColor: "#1e2329"
        },
        horzLine: {
          color: "rgba(234, 236, 239, 0.45)",
          labelBackgroundColor: "#1e2329"
        }
      },
      rightPriceScale: {
        visible: true,
        borderColor: "rgba(132, 142, 156, 0.24)",
        borderVisible: true,
        ticksVisible: true,
        minimumWidth: 82,
        ensureEdgeTickMarksVisible: true,
        scaleMargins: { top: 0.08, bottom: 0.24 }
      },
      timeScale: {
        borderColor: "rgba(132, 142, 156, 0.24)",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 12,
        barSpacing: 9,
        minBarSpacing: 3
      },
      localization: {
        priceFormatter: (price: number) => formatPrice(price)
      }
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#0ecb81",
      downColor: "#f6465d",
      borderUpColor: "#0ecb81",
      borderDownColor: "#f6465d",
      wickUpColor: "#0ecb81",
      wickDownColor: "#f6465d",
      priceLineVisible: true,
      priceLineColor: "#f0b90b",
      priceLineWidth: 1,
      lastValueVisible: true
    });
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      color: "rgba(132, 142, 156, 0.45)",
      lastValueVisible: false,
      priceLineVisible: false
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 }
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;

    const handleCrosshairMove = (param: MouseEventParams<Time>) => {
      const item = param.seriesData.get(candleSeries) as { open: number; high: number; low: number; close: number; time: Time } | undefined;
      if (!item) {
        setHoverInfo(null);
        return;
      }
      const source = validCandles.find((candle) => toChartTime(candle.time) === item.time);
      setHoverInfo({
        time: source?.time ?? chartTimeToIso(item.time),
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
        volume: source?.volume ?? 0
      });
    };
    chart.subscribeCrosshairMove(handleCrosshairMove);

    return () => {
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      markerRef.current = null;
      highPriceLineRef.current = null;
      lowPriceLineRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    const candleSeries = candleSeriesRef.current;
    if (!chart || !candleSeries) return;
    if (!validCandles.length) {
      candleSeries.setData([]);
      return;
    }

    const candleData = validCandles.map((candle) => ({
      time: toChartTime(candle.time),
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close
    }));
    candleSeries.setData(candleData);
    updateHighLowPriceLines(candleSeries, highPriceLineRef, lowPriceLineRef, validCandles);

    const volumeSeries = chart.panes()[0].getSeries().find((series) => series.seriesType() === "Histogram") as ISeriesApi<"Histogram"> | undefined;
    volumeSeries?.setData(
      validCandles.map((candle) => ({
        time: toChartTime(candle.time),
        value: candle.volume,
        color: candle.close >= candle.open ? "rgba(14, 203, 129, 0.35)" : "rgba(246, 70, 93, 0.35)"
      }))
    );

    addMovingAverage(chart, validCandles, "ma5", "#f0b90b");
    addMovingAverage(chart, validCandles, "ma20", "#4f8cff");
    addMovingAverage(chart, validCandles, "ma60", "#d36bff");

    let markers: SeriesMarker<Time>[] = [];
    if (signalTime) {
      const markerTime = nearestChartTime(validCandles, signalTime);
      if (markerTime) {
        markers = [
          {
            time: markerTime,
            position: "aboveBar",
            color: "#f0b90b",
            shape: "arrowDown",
            text: "信号"
          }
        ];
      }
    }
    if (!markerRef.current) {
      markerRef.current = createSeriesMarkers(candleSeries, markers);
    } else {
      markerRef.current.setMarkers(markers);
    }

    chart.timeScale().fitContent();
  }, [signalTime, validCandles]);

  return (
    <div className="market-chart-shell">
      <div className="market-chart-header">
        <div className={`market-chart-meta ${displayDirection}`}>
          {displayInfo ? (
            <>
              <span>{formatDateTime(displayInfo.time)}</span>
              <span>O {formatPrice(displayInfo.open)}</span>
              <span>H {formatPrice(displayInfo.high)}</span>
              <span>L {formatPrice(displayInfo.low)}</span>
              <span>C {formatPrice(displayInfo.close)}</span>
              <span>V {Math.round(displayInfo.volume).toLocaleString()}</span>
            </>
          ) : (
            <span>暂无行情</span>
          )}
        </div>
        <div className="market-chart-legend" aria-label="均线">
          <span className="ma5">MA5</span>
          <span className="ma20">MA20</span>
          <span className="ma60">MA60</span>
          <span>{validCandles.length} 根</span>
          <span>{dataRangeLabel}</span>
        </div>
        {chartHeaderExtra ? <div className="market-chart-extra">{chartHeaderExtra}</div> : null}
      </div>
      <div className="market-chart" ref={containerRef} />
      {loading ? <div className="chart-overlay">正在加载 K 线...</div> : null}
      {!loading && !validCandles.length ? <div className="chart-overlay">暂无该周期 K 线数据</div> : null}
    </div>
  );
}

function addMovingAverage(chart: IChartApi, candles: Candle[], key: "ma5" | "ma20" | "ma60", color: string) {
  const existing = chart.panes()[0].getSeries().filter((series) => series.seriesType() === "Line");
  const index = key === "ma5" ? 0 : key === "ma20" ? 1 : 2;
  const series = (existing[index] as ISeriesApi<"Line"> | undefined) ?? chart.addSeries(LineSeries, {
    color,
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
    crosshairMarkerVisible: false
  });
  series.applyOptions({ color, lineWidth: 2 });
  series.setData(
    candles
      .filter((candle) => Number.isFinite(candle[key]) && candle[key] > 0)
      .map((candle) => ({ time: toChartTime(candle.time), value: candle[key] }))
  );
}

function updateHighLowPriceLines(
  series: ISeriesApi<"Candlestick">,
  highRef: MutableRefObject<IPriceLine | null>,
  lowRef: MutableRefObject<IPriceLine | null>,
  candles: Candle[]
) {
  if (highRef.current) {
    series.removePriceLine(highRef.current);
    highRef.current = null;
  }
  if (lowRef.current) {
    series.removePriceLine(lowRef.current);
    lowRef.current = null;
  }
  if (!candles.length) return;

  const highest = candles.reduce((best, candle) => (candle.high > best.high ? candle : best), candles[0]);
  const lowest = candles.reduce((best, candle) => (candle.low < best.low ? candle : best), candles[0]);
  highRef.current = series.createPriceLine({
    price: highest.high,
    color: "#f0b90b",
    lineWidth: 1,
    lineStyle: LineStyle.Dashed,
    lineVisible: true,
    axisLabelVisible: true,
    title: `高 ${formatPrice(highest.high)}`
  });
  lowRef.current = series.createPriceLine({
    price: lowest.low,
    color: "#848e9c",
    lineWidth: 1,
    lineStyle: LineStyle.Dashed,
    lineVisible: true,
    axisLabelVisible: true,
    title: `低 ${formatPrice(lowest.low)}`
  });
}

function toChartTime(value: string): UTCTimestamp {
  const timestamp = Math.floor(new Date(value).getTime() / 1000);
  return timestamp as UTCTimestamp;
}

function chartTimeToIso(value: Time): string {
  if (typeof value === "number") {
    return new Date(value * 1000).toISOString();
  }
  if (typeof value === "string") {
    return value;
  }
  return new Date(Date.UTC(value.year, value.month - 1, value.day)).toISOString();
}

function nearestChartTime(candles: Candle[], signalTime: string): UTCTimestamp | null {
  const target = new Date(signalTime).getTime();
  if (Number.isNaN(target) || !candles.length) return null;
  let nearest = candles[0];
  let distance = Math.abs(new Date(nearest.time).getTime() - target);
  for (const candle of candles) {
    const nextDistance = Math.abs(new Date(candle.time).getTime() - target);
    if (nextDistance < distance) {
      nearest = candle;
      distance = nextDistance;
    }
  }
  return toChartTime(nearest.time);
}
