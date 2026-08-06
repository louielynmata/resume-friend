import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";
import {
  notifyWhenGenerationCompletes,
  requestDesktopNotificationPermission,
  showGenerationCompleteNotification,
} from "../src/utils/desktop-notification.js";

interface CapturedNotification {
  title: string;
  options?: NotificationOptions;
}

class FakeNotification {
  static permission: NotificationPermission = "default";
  static permissionRequests = 0;
  static notifications: CapturedNotification[] = [];

  static async requestPermission(): Promise<NotificationPermission> {
    FakeNotification.permissionRequests += 1;
    return "granted";
  }

  constructor(title: string, options?: NotificationOptions) {
    FakeNotification.notifications.push({ title, options });
  }
}

const originalNotification = globalThis.Notification;

describe("desktop completion notifications", () => {
  beforeEach(() => {
    FakeNotification.permission = "default";
    FakeNotification.permissionRequests = 0;
    FakeNotification.notifications = [];
    globalThis.Notification = FakeNotification as unknown as typeof Notification;
  });

  afterEach(() => {
    if (originalNotification) {
      globalThis.Notification = originalNotification;
    } else {
      Reflect.deleteProperty(globalThis, "Notification");
    }
  });

  it("requests permission once when the browser has not made a decision", async () => {
    const enabled = await requestDesktopNotificationPermission();

    assert.equal(enabled, true);
    assert.equal(FakeNotification.permissionRequests, 1);
  });

  it("shows the successful job context when permission is granted", () => {
    FakeNotification.permission = "granted";

    const shown = showGenerationCompleteNotification({
      position: "Product Designer",
      company: "Example Co",
    });

    assert.equal(shown, true);
    assert.deepEqual(FakeNotification.notifications, [
      {
        title: "Resume Friend is finished",
        options: {
          body: "Product Designer at Example Co is ready.",
          icon: "/favicon.svg",
          tag: "resume-friend-generation-complete",
        },
      },
    ]);
  });

  it("notifies only after generation resolves and preserves its result", async () => {
    FakeNotification.permission = "granted";
    const generationResult = { outputFolder: "/outputs/example" };

    const result = await notifyWhenGenerationCompletes(
      Promise.resolve(generationResult),
      { position: "Product Designer", company: "Example Co" },
    );

    assert.equal(result, generationResult);
    assert.equal(FakeNotification.notifications.length, 1);
  });

  it("does not announce a failed generation", async () => {
    FakeNotification.permission = "granted";
    const failure = new Error("QA failed");

    await assert.rejects(
      notifyWhenGenerationCompletes(Promise.reject(failure), {
        position: "Product Designer",
        company: "Example Co",
      }),
      failure,
    );
    assert.deepEqual(FakeNotification.notifications, []);
  });

  it("does not create a notification after permission is denied", () => {
    FakeNotification.permission = "denied";

    assert.equal(
      showGenerationCompleteNotification({
        position: "Product Designer",
        company: "Example Co",
      }),
      false,
    );
    assert.deepEqual(FakeNotification.notifications, []);
  });

  it("does not block generation in browsers without notification support", async () => {
    Reflect.deleteProperty(globalThis, "Notification");

    assert.equal(await requestDesktopNotificationPermission(), false);
    assert.equal(
      showGenerationCompleteNotification({
        position: "Product Designer",
        company: "Example Co",
      }),
      false,
    );
  });
});
