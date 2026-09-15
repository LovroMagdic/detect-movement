import { useEffect, useRef, useState } from "react";

import { useToast } from "../context/ToastContext";
import { extractFirstFrame, type FirstFrameData } from "../lib/videoFrame";
import type { WatermarkRect } from "../api/client";

interface UploadPanelProps {
  onSubmit: (
    file: File,
    options: { useWatermarkZone: boolean; watermarkRect: WatermarkRect | null }
  ) => void | Promise<void>;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function normalizeRect(start: { x: number; y: number }, end: { x: number; y: number }): WatermarkRect {
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  return {
    x,
    y,
    width: Math.abs(end.x - start.x),
    height: Math.abs(end.y - start.y)
  };
}

function hasValidWatermark(rect: WatermarkRect | null): rect is WatermarkRect {
  return rect != null && rect.width >= 2 && rect.height >= 2;
}

export default function UploadPanel({ onSubmit }: UploadPanelProps) {
  const { showError } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [firstFrame, setFirstFrame] = useState<FirstFrameData | null>(null);
  const [watermarkRect, setWatermarkRect] = useState<WatermarkRect | null>(null);
  const [draftRect, setDraftRect] = useState<WatermarkRect | null>(null);
  const frameRequestRef = useRef(0);
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);
  const frameImgRef = useRef<HTMLImageElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const canStart = !!file;
  const shownRect = draftRect ?? watermarkRect;

  useEffect(() => {
    if (!file) {
      setFirstFrame(null);
      setWatermarkRect(null);
      setDraftRect(null);
      return;
    }
    const reqId = frameRequestRef.current + 1;
    frameRequestRef.current = reqId;
    setFirstFrame(null);
    setWatermarkRect(null);
    setDraftRect(null);

    void extractFirstFrame(file)
      .then((frame) => {
        if (frameRequestRef.current !== reqId) return;
        setFirstFrame(frame);
      })
      .catch((frameErr) => {
        if (frameRequestRef.current !== reqId) return;
        showError((frameErr as Error).message);
      });
  }, [file, showError]);

  const getPointerPoint = (evt: React.PointerEvent): { x: number; y: number } | null => {
    if (!firstFrame || !frameImgRef.current) return null;
    const bounds = frameImgRef.current.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return null;
    const relX = clamp(evt.clientX - bounds.left, 0, bounds.width);
    const relY = clamp(evt.clientY - bounds.top, 0, bounds.height);
    return {
      x: (relX / bounds.width) * firstFrame.width,
      y: (relY / bounds.height) * firstFrame.height
    };
  };

  const completeSelection = (evt?: React.PointerEvent<HTMLDivElement>) => {
    const start = dragStartRef.current;
    if (!start) return;
    let next = draftRect;
    if (evt) {
      const point = getPointerPoint(evt);
      if (point) next = normalizeRect(start, point);
    }
    dragStartRef.current = null;
    setDraftRect(null);
    if (!hasValidWatermark(next)) {
      setWatermarkRect(null);
      return;
    }
    setWatermarkRect(next);
  };

  function resetForm() {
    frameRequestRef.current += 1;
    setFile(null);
    setFirstFrame(null);
    setWatermarkRect(null);
    setDraftRect(null);
    dragStartRef.current = null;
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    const useWatermark = hasValidWatermark(watermarkRect);
    try {
      await onSubmit(file, {
        useWatermarkZone: useWatermark,
        watermarkRect: useWatermark ? watermarkRect : null
      });
      resetForm();
    } catch {
    }
  }

  return (
    <section className="upload-panel">
      <h2 className="upload-panel-title">New analysis</h2>
      <form className="upload-form" onSubmit={handleSubmit}>
        <div className="upload-row">
          <input
            ref={fileInputRef}
            type="file"
            accept="video/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {file && (
          <div className="watermark-picker">
            <p className="status-subtle">
              Optional: draw a rectangle on the preview to mark the watermark area. Leave blank to process the full
              frame.
            </p>
            {!firstFrame && <p className="status-subtle">Loading preview frame...</p>}
            {firstFrame && (
              <>
                <div
                  className="first-frame-canvas"
                  onPointerDown={(evt) => {
                    const point = getPointerPoint(evt);
                    if (!point) return;
                    dragStartRef.current = point;
                    setDraftRect({ x: point.x, y: point.y, width: 0, height: 0 });
                    evt.currentTarget.setPointerCapture(evt.pointerId);
                  }}
                  onPointerMove={(evt) => {
                    if (!dragStartRef.current) return;
                    const point = getPointerPoint(evt);
                    if (!point) return;
                    setDraftRect(normalizeRect(dragStartRef.current, point));
                  }}
                  onPointerUp={(evt) => completeSelection(evt)}
                  onPointerLeave={(evt) => completeSelection(evt)}
                >
                  <img ref={frameImgRef} src={firstFrame.src} alt="Preview frame" draggable={false} />
                  {shownRect && (
                    <div
                      className="watermark-rect"
                      style={{
                        left: `${(shownRect.x / firstFrame.width) * 100}%`,
                        top: `${(shownRect.y / firstFrame.height) * 100}%`,
                        width: `${(shownRect.width / firstFrame.width) * 100}%`,
                        height: `${(shownRect.height / firstFrame.height) * 100}%`
                      }}
                    ></div>
                  )}
                </div>
                <div className="watermark-actions">
                  <button
                    type="button"
                    onClick={() => {
                      setWatermarkRect(null);
                      setDraftRect(null);
                    }}
                    disabled={!watermarkRect}
                  >
                    Clear selection
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {file && (
          <div className="upload-submit-row">
            <button disabled={!canStart} type="submit">
              Upload and Process
            </button>
          </div>
        )}
      </form>
    </section>
  );
}

