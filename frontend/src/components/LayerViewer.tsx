import { useEffect, useMemo, useRef, useState } from "react";

import type { LayerMode } from "../api/client";

interface LayerViewerProps {
  mapUrl: string;
  heatmapUrl: string;
  mode: LayerMode;
}

export default function LayerViewer({ mapUrl, heatmapUrl, mode }: LayerViewerProps) {
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const viewerRef = useRef<HTMLDivElement | null>(null);
  const dragStartRef = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);

  const shouldShowMap = mode === "map" || mode === "both";
  const shouldShowHeatmap = mode === "heatmap" || mode === "both";

  const transform = useMemo(
    () => `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`,
    [offset.x, offset.y, zoom]
  );

  useEffect(() => {
    const el = viewerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const step = e.deltaY < 0 ? 1.1 : 0.9;
      setZoom((z) => Math.max(0.2, Math.min(8, z * step)));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const onMouseDown: React.MouseEventHandler<HTMLDivElement> = (e) => {
    setDragging(true);
    dragStartRef.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y };
  };

  const onMouseMove: React.MouseEventHandler<HTMLDivElement> = (e) => {
    if (!dragging || !dragStartRef.current) return;
    const { x, y, ox, oy } = dragStartRef.current;
    setOffset({ x: ox + (e.clientX - x), y: oy + (e.clientY - y) });
  };

  const onMouseUp: React.MouseEventHandler<HTMLDivElement> = () => {
    setDragging(false);
    dragStartRef.current = null;
  };

  return (
    <div>
      <div className="viewer-controls">
        <button onClick={() => setZoom((z) => Math.min(8, z * 1.2))}>Zoom In</button>
        <button onClick={() => setZoom((z) => Math.max(0.2, z / 1.2))}>Zoom Out</button>
        <button
          onClick={() => {
            setZoom(1);
            setOffset({ x: 0, y: 0 });
          }}
        >
          Reset
        </button>
        <span>Zoom: {zoom.toFixed(2)}x</span>
      </div>
      <div
        ref={viewerRef}
        className="viewer"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <div className="layer-stack" style={{ transform }}>
          {shouldShowMap && <img className="layer-img" src={mapUrl} alt="stitched map" draggable={false} />}
          {shouldShowHeatmap && (
            <img
              className={`layer-img ${mode === "both" ? "heatmap-overlay" : ""}`}
              src={heatmapUrl}
              alt="heatmap"
              draggable={false}
            />
          )}
        </div>
      </div>
    </div>
  );
}

