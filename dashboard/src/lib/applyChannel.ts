/** Job boards that have no fillable application form we can prefill. */

const LINK_ONLY_HOSTS = [
  "linkedin.com",
  "naukri.com",
  "indeed.com",
  "glassdoor.com",
  "glassdoor.co.in",
  "monster.com",
  "foundit.in",
  "shine.com",
  "timesjobs.com",
  "dice.com",
  "ziprecruiter.com",
  "simplyhired.com",
  "instahyre.com",
  "hirist.tech",
  "hirist.com",
  "cutshort.io",
  "iimjobs.com",
  "wellfound.com",
  "angel.co",
];

const LINK_ONLY_SOURCE = [
  "linkedin",
  "naukri",
  "indeed",
  "glassdoor",
  "monster",
  "foundit",
  "shine",
  "timesjobs",
  "dice",
  "ziprecruiter",
  "instahyre",
  "hirist",
  "cutshort",
  "iimjobs",
  "wellfound",
];

function hostOf(url: string): string {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host.startsWith("www.") ? host.slice(4) : host;
  } catch {
    return "";
  }
}

export type ApplyChannelJob = {
  apply_channel?: string | null;
  url?: string | null;
  source?: string | null;
};

/** True when Prefill must be hidden — Open posting only. */
export function isLinkOnlyJob(job?: ApplyChannelJob | null): boolean {
  if (!job) return false;
  if (job.apply_channel === "link") return true;
  if (job.apply_channel === "email" || job.apply_channel === "form" || job.apply_channel === "manual") {
    return false;
  }
  const host = hostOf(String(job.url || ""));
  if (host && LINK_ONLY_HOSTS.some((h) => host === h || host.endsWith("." + h))) {
    return true;
  }
  const src = String(job.source || "").toLowerCase();
  return LINK_ONLY_SOURCE.some((k) => src.includes(k));
}

export function resolveApplyChannel(job?: ApplyChannelJob | null): string {
  if (!job) return "manual";
  if (job.apply_channel === "email" || job.apply_channel === "form" || job.apply_channel === "manual" || job.apply_channel === "link") {
    return job.apply_channel;
  }
  if (isLinkOnlyJob(job)) return "link";
  if (String(job.url || "").trim()) return "form";
  return "manual";
}
