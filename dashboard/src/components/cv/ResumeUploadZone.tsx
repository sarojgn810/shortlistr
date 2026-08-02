"use client";

import { useCallback, useRef, useState } from "react";
import { Upload, FileText } from "lucide-react";
import { Button } from "@/src/components/ui/Button";

const ACCEPT = ".pdf,.docx,.doc,.txt,.md,.markdown";

interface ResumeUploadZoneProps {
  disabled?: boolean;
  onUpload: (file: File) => Promise<void>;
}

export function ResumeUploadZone({ disabled, onUpload }: ResumeUploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

  const handleFile = useCallback(
    async (file: File | undefined) => {
      if (!file || disabled || uploading) return;
      setFileName(file.name);
      setUploading(true);
      try {
        await onUpload(file);
      } finally {
        setUploading(false);
      }
    },
    [disabled, onUpload, uploading]
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    void handleFile(file);
  };

  return (
    <div className="space-y-3">
      <div
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${
          dragOver
            ? "border-lime bg-lime/10"
            : "border-mist bg-sage/20 hover:border-lime/40 hover:bg-sage/30"
        } ${disabled || uploading ? "pointer-events-none opacity-60" : ""}`}
      >
        <div className="rounded-full bg-white p-3 shadow-sm">
          <Upload className="text-ink" size={28} />
        </div>
        <div>
          <p className="font-bold text-ink">
            {uploading ? "Extracting your resume…" : "Drop your resume here"}
          </p>
          <p className="mt-1 text-base text-stone">PDF, Word (.docx), or text — max 10 MB</p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          isLoading={uploading}
          onClick={(e) => {
            e.stopPropagation();
            inputRef.current?.click();
          }}
        >
          Choose file
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => void handleFile(e.target.files?.[0])}
        />
      </div>
      {fileName && !uploading && (
        <p className="flex items-center gap-2 text-sm text-stone">
          <FileText size={14} />
          Last file: <span className="font-mono text-ink">{fileName}</span>
        </p>
      )}
    </div>
  );
}
