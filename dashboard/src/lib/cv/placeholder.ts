/** Detect default onboarding CV template (mirrors automation/cv/placeholder.py). */

const PLACEHOLDER_MARKERS = [
  "# your name",
  "email@example.com",
  "linkedin.com/in/you",
  "your title | company",
  "your role, years of experience",
  "degree | school | years",
  "one measurable win",
  "bullet with a metric",
];

export function isPlaceholderCv(md: string): boolean {
  if (!md?.trim()) return true;
  const lower = md.toLowerCase();
  const hits = PLACEHOLDER_MARKERS.filter((m) => lower.includes(m)).length;
  return hits >= 3;
}
