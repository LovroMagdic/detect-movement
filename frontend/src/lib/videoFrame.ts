export interface FirstFrameData {
  src: string;
  width: number;
  height: number;
}

export function extractFirstFrame(file: File): Promise<FirstFrameData> {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.src = objectUrl;
    video.muted = true;
    video.playsInline = true;

    const cleanup = () => {
      URL.revokeObjectURL(objectUrl);
      video.removeAttribute("src");
      video.load();
    };

    let done = false;
    const resolveFrame = () => {
      if (done) return;
      done = true;
      const width = video.videoWidth;
      const height = video.videoHeight;
      if (!width || !height) {
        cleanup();
        reject(new Error("Could not read video dimensions from the selected file."));
        return;
      }

      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        cleanup();
        reject(new Error("Could not create canvas context for frame extraction."));
        return;
      }

      ctx.drawImage(video, 0, 0, width, height);
      const src = canvas.toDataURL("image/jpeg", 0.92);
      cleanup();
      resolve({ src, width, height });
    };

    video.onloadedmetadata = () => {
      const duration = Number.isFinite(video.duration) ? video.duration : 0;
      const maxPreviewSecond = Math.min(2, duration > 0 ? duration : 2);
      const upperBound = Math.max(0, maxPreviewSecond - 0.05);
      const randomSecond = upperBound > 0 ? Math.random() * upperBound : 0;
      if (randomSecond <= 0.01) {
        if (video.readyState >= 2) {
          resolveFrame();
          return;
        }
        video.onloadeddata = resolveFrame;
        return;
      }
      video.onseeked = resolveFrame;
      video.currentTime = randomSecond;
    };

    video.onerror = () => {
      if (done) return;
      done = true;
      cleanup();
      reject(new Error("Could not load the selected video."));
    };
  });
}
