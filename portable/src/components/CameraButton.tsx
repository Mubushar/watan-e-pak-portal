/**
 * "Camera" for site photos: on phones / tablets the device camera opens (input capture); on a PC
 * a webcam window opens (getUserMedia), with the file picker as a fallback. Every photo is
 * downscaled to a JPEG data URL (compressImage) before it is uploaded.
 */
import { useEffect, useRef, useState } from "react";
import { Camera, X } from "lucide-react";
import { toast } from "sonner";
import { compressImage } from "@/lib/images";
import { touchDevice } from "@/lib/device";
import { cn } from "@/lib/utils";

export function CameraButton({ onPhotos, className, label = "Camera", multiple }: { onPhotos: (dataUrls: string[]) => void; className?: string; label?: string; multiple?: boolean }) {
  const [webcam, setWebcam] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const fromFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    try {
      onPhotos(await Promise.all(Array.from(files).map((f) => compressImage(f))));
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  return (
    <>
      <button
        type="button"
        onClick={() => (touchDevice() || !navigator.mediaDevices?.getUserMedia ? fileRef.current?.click() : setWebcam(true))}
        className={cn("flex flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-brand-300 text-brand-700 transition hover:bg-brand-50 dark:border-white/20 dark:text-brand-200 dark:hover:bg-white/5", className)}
      >
        <Camera className="h-6 w-6" />
        <span className="text-xs font-semibold">{label}</span>
      </button>
      <input ref={fileRef} type="file" accept="image/*" capture="environment" multiple={multiple} className="hidden" onChange={(e) => void fromFiles(e.target.files).finally(() => (e.target.value = ""))} />
      {webcam && <Webcam onClose={() => setWebcam(false)} onShot={(u) => onPhotos([u])} onFallback={() => fileRef.current?.click()} />}
    </>
  );
}

function Webcam({ onClose, onShot, onFallback }: { onClose: () => void; onShot: (dataUrl: string) => void; onFallback: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let stream: MediaStream | null = null;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment", width: { ideal: 1600 } }, audio: false })
      .then((s) => {
        stream = s;
        if (video.current) {
          video.current.srcObject = s;
          void video.current.play();
        }
        setReady(true);
      })
      .catch(() => {
        toast.error("No camera available — choose a photo instead");
        onClose();
        onFallback();
      });
    return () => stream?.getTracks().forEach((t) => t.stop());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const shoot = () => {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const scale = Math.min(1, 1600 / Math.max(v.videoWidth, v.videoHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(v.videoWidth * scale);
    c.height = Math.round(v.videoHeight * scale);
    c.getContext("2d")!.drawImage(v, 0, 0, c.width, c.height);
    onShot(c.toDataURL("image/jpeg", 0.82));
    toast.success("Photo added");
  };
  return (
    <div className="fixed inset-0 z-[1000] flex flex-col bg-black">
      <video ref={video} playsInline muted className="min-h-0 flex-1 object-contain" />
      <div className="flex items-center justify-between gap-3 p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <button type="button" onClick={onClose} className="btn btn-ghost text-white" aria-label="Close camera">
          <X className="h-5 w-5" /> Done
        </button>
        <button type="button" disabled={!ready} onClick={shoot} className="h-16 w-16 rounded-full border-4 border-white bg-white/20 disabled:opacity-40" aria-label="Take photo" />
        <span className="w-20" />
      </div>
    </div>
  );
}
