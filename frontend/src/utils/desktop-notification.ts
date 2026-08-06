export async function requestDesktopNotificationPermission(): Promise<boolean> {
  if (typeof Notification === "undefined") return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission !== "default") return false;

  try {
    return (await Notification.requestPermission()) === "granted";
  } catch {
    return false;
  }
}

export function showGenerationCompleteNotification(job: {
  position: string;
  company: string;
}): boolean {
  if (
    typeof Notification === "undefined" ||
    Notification.permission !== "granted"
  ) {
    return false;
  }

  const position = job.position.trim();
  const company = job.company.trim();
  const subject = [position, company].filter(Boolean).join(" at ");

  try {
    new Notification("Resume Friend is finished", {
      body: subject ? `${subject} is ready.` : "Your documents are ready.",
      icon: "/favicon.svg",
      tag: "resume-friend-generation-complete",
    });
    return true;
  } catch {
    return false;
  }
}

export async function notifyWhenGenerationCompletes<T>(
  generation: Promise<T>,
  job: { position: string; company: string },
): Promise<T> {
  const result = await generation;
  showGenerationCompleteNotification(job);
  return result;
}
