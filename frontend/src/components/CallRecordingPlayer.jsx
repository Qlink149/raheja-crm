import { useCallback, useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import { Button } from "./ui/button";
import { formatDuration } from "../lib/formatDuration";

/**
 * Compact seekable player for call recordings (avoids native controls overflow).
 */
export default function CallRecordingPlayer({ src, testId }) {
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    setIsPlaying(false);
    setProgress(0);
    setDuration(0);
  }, [src]);

  const handlePlayPause = useCallback(() => {
    const el = audioRef.current;
    if (!el) return;
    if (isPlaying) el.pause();
    else el.play();
    setIsPlaying(!isPlaying);
  }, [isPlaying]);

  const handleSeek = useCallback(
    (e) => {
      const el = audioRef.current;
      if (!el || !duration) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const percent = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      el.currentTime = percent * duration;
      setProgress(el.currentTime);
    },
    [duration]
  );

  if (!src) {
    return <p className="text-xs text-[#525252] italic">Recording unavailable.</p>;
  }

  return (
    <div className="w-full min-w-0" data-testid={testId}>
      <div className="flex items-center gap-3 min-w-0">
        <Button
          type="button"
          size="icon"
          onClick={handlePlayPause}
          className="w-10 h-10 rounded-full bg-[#C5A059] hover:bg-[#E5C585] text-black btn-tactile flex-shrink-0"
          aria-label={isPlaying ? "Pause" : "Play"}
        >
          {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
        </Button>
        <div className="flex-1 min-w-0">
          <div
            className="h-2 bg-white/10 rounded-full cursor-pointer relative overflow-hidden touch-pan-x"
            onClick={handleSeek}
            role="slider"
            aria-valuemin={0}
            aria-valuemax={duration}
            aria-valuenow={progress}
          >
            <div
              className="absolute inset-y-0 left-0 bg-gradient-to-r from-[#C5A059] to-[#E5C585] rounded-full transition-all duration-150"
              style={{ width: `${duration ? (progress / duration) * 100 : 0}%` }}
            />
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-xs text-[#A3A3A3] tabular-nums">{formatDuration(Math.floor(progress))}</span>
            <span className="text-xs text-[#A3A3A3] tabular-nums">{formatDuration(Math.floor(duration))}</span>
          </div>
        </div>
      </div>
      <audio
        ref={audioRef}
        src={src}
        className="hidden"
        preload="metadata"
        onTimeUpdate={() => {
          if (audioRef.current) setProgress(audioRef.current.currentTime);
        }}
        onLoadedMetadata={() => {
          if (audioRef.current) setDuration(audioRef.current.duration || 0);
        }}
        onEnded={() => setIsPlaying(false)}
      />
    </div>
  );
}
