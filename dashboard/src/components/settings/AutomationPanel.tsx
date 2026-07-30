"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/src/components/ui/Button";
import { api, type AutomationSettings } from "@/src/lib/api/client";

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "Never";
  try {
    const d = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z");
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

export default function AutomationPanel() {
  const [settings, setSettings] = useState<AutomationSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [scanning, setScanning] = useState(false);

  const load = async () => {
    try {
      setSettings(await api.getAutomation());
    } catch {
      setSettings(null);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (!settings) {
    return (
      <p className="text-base text-orange">
        Shortlistr isn’t running yet. Open it with the Start app shortcut, then come back here.
      </p>
    );
  }

  const save = async () => {
    setSaving(true);
    try {
      const next = await api.setAutomation(settings);
      setSettings(next);
      toast.success("Saved");
    } catch {
      toast.error("Couldn’t save — is Shortlistr running?");
    } finally {
      setSaving(false);
    }
  };

  const runNow = async () => {
    setScanning(true);
    try {
      await api.runScheduledScan(false, true);
      toast.success("Scan started — new jobs will appear on Discover");
      await load();
    } catch {
      toast.error("Couldn’t start a scan");
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-5">
      <label className="flex cursor-pointer items-start gap-3">
        <input
          type="checkbox"
          checked={settings.scan_enabled}
          onChange={(e) => setSettings({ ...settings, scan_enabled: e.target.checked })}
          className="mt-1 h-5 w-5 shrink-0"
        />
        <span>
          <span className="block text-base font-bold text-ink">Find new jobs automatically</span>
          <span className="mt-1 block text-sm leading-relaxed text-stone">
            Shortlistr checks job boards in the background while the app is open. Turn off if you only want to scan by hand.
          </span>
        </span>
      </label>

      <div className="space-y-1.5 pl-8">
        <label className="block text-sm font-semibold text-ink">How often?</label>
        <select
          value={settings.scan_interval_hours}
          onChange={(e) =>
            setSettings({ ...settings, scan_interval_hours: Number(e.target.value) || 72 })
          }
          disabled={!settings.scan_enabled}
          className="w-full max-w-sm rounded-xl border border-mist bg-white px-3.5 py-2.5 text-base text-ink outline-none focus:border-lime/60 disabled:opacity-50"
        >
          <option value={24}>Every day</option>
          <option value={48}>Every 2 days</option>
          <option value={72}>Every 3 days (recommended)</option>
          <option value={120}>Every 5 days</option>
          <option value={168}>Once a week</option>
        </select>
      </div>

      <label className="flex cursor-pointer items-start gap-3">
        <input
          type="checkbox"
          checked={settings.auto_evaluate}
          onChange={(e) => setSettings({ ...settings, auto_evaluate: e.target.checked })}
          className="mt-1 h-5 w-5 shrink-0"
        />
        <span>
          <span className="block text-base font-bold text-ink">Score new jobs for me</span>
          <span className="mt-1 block text-sm leading-relaxed text-stone">
            After a scan, Shortlistr rates how well each role fits you. You still approve before anything is applied.
          </span>
        </span>
      </label>

      <p className="rounded-xl bg-mist/40 px-4 py-3 text-sm text-stone">
        Last scan:{" "}
        <strong className="text-ink">{formatWhen(settings.last_scan_at)}</strong>
        {settings.scan_due ? " · due now" : ""}
      </p>

      <div className="flex flex-wrap gap-2">
        <Button variant="lime" size="sm" onClick={save} isLoading={saving}>
          Save
        </Button>
        <Button variant="secondary" size="sm" onClick={runNow} isLoading={scanning}>
          Find jobs now
        </Button>
      </div>
    </div>
  );
}
