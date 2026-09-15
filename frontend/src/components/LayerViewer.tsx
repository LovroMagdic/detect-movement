import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import LayerViewerSkeleton from "./LayerViewerSkeleton";
import { useToast } from "../context/ToastContext";

interface LayerViewerProps {
  mapUrl: string;
  heatmapUrl: string;
  forestOverlayUrl: string;
  showMap: boolean;
  showHeatmap: boolean;
  showForest: boolean;
}

export default function LayerViewer({
  mapUrl,
  heatmapUrl,
  forestOverlayUrl,
  showMap,
  showHeatmap,
  showForest
}: LayerViewerProps) {
  const { showError } = useToast();
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [layersReady, setLayersReady] = useState(false);
  const viewerRef = useRef<HTMLDivElement | null>(null);
  const baseImgRef = useRef<HTMLImageElement | null>(null);
  const heatmapImgRef = useRef<HTMLImageElement | null>(null);
  const dragStartRef = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const toastedLayersRef = useRef<Set<string>>(new Set());
  const loadedLayersRef = useRef<Set<string>>(new Set());

  const baseUrl = showForest ? forestOverlayUrl : mapUrl;
  const shouldShowBase = showMap || showForest;
  const shouldShowHeatmap = showHeatmap;
  const activeLayerCount = (shouldShowBase ? 1 : 0) + (shouldShowHeatmap ? 1 : 0);

  const transform = useMemo(
    () => `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`,
    [offset.x, offset.y, zoom]
  );

  const isImgLoaded = (img: HTMLImageElement | null) =>
    Boolean(img?.complete && img.naturalWidth > 0);

  const syncLayersReady = useCallback(() => {
    const loaded = new Set<string>();
    if (shouldShowBase && isImgLoaded(baseImgRef.current)) loaded.add("base");
    if (shouldShowHeatmap && isImgLoaded(heatmapImgRef.current)) loaded.add("heatmap");
    loadedLayersRef.current = loaded;
    setLayersReady(activeLayerCount === 0 || loaded.size >= activeLayerCount);
  }, [activeLayerCount, shouldShowBase, shouldShowHeatmap]);

  const markLayerLoaded = (layer: string) => {
    loadedLayersRef.current.add(layer);
    if (loadedLayersRef.current.size >= activeLayerCount && activeLayerCount > 0) {
      setLayersReady(true);
    }
  };

  const handleLayerError = (layer: "base" | "heatmap") => {
    if (toastedLayersRef.current.has(layer)) return;
    toastedLayersRef.current.add(layer);
    showError(layer === "heatmap" ? "Could not load heatmap layer" : "Could not load map layer");
    markLayerLoaded(layer);
  };

  useLayoutEffect(() => {
    toastedLayersRef.current.clear();
    syncLayersReady();
  }, [mapUrl, heatmapUrl, forestOverlayUrl, syncLayersReady]);

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
        <button
          onClick={() => {
            setZoom(1);
            setOffset({ x: 0, y: 0 });
          }}
        >
          Reset
        </button>
      </div>
      <div
        ref={viewerRef}
        className="viewer viewer-with-skeleton"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        {!layersReady && <LayerViewerSkeleton />}
        <div className={`layer-stack ${layersReady ? "layer-stack-visible" : "layer-stack-hidden"}`} style={{ transform }}>
          {shouldShowBase && (
            <img
              ref={baseImgRef}
              key={baseUrl}
              className="layer-img"
              src={baseUrl}
              alt={showForest ? "segmentation overlay map" : "base map"}
              draggable={false}
              onLoad={() => markLayerLoaded("base")}
              onError={() => handleLayerError("base")}
            />
          )}
          {shouldShowHeatmap && (
            <img
              ref={heatmapImgRef}
              key={heatmapUrl}
              className={`layer-img ${shouldShowBase ? "heatmap-overlay" : ""}`}
              src={heatmapUrl}
              alt="dead-tree heatmap"
              draggable={false}
              onLoad={() => markLayerLoaded("heatmap")}
              onError={() => handleLayerError("heatmap")}
            />
          )}
        </div>
      </div>
    </div>
  );
}
