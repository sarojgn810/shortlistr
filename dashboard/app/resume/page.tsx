import { redirect } from "next/navigation";

/** Legacy bookmark — Resume lives at /cv. */
export default function ResumeRedirectPage() {
  redirect("/cv");
}
