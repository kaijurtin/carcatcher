import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AiToggle } from "./AiToggle";

afterEach(() => vi.restoreAllMocks());

function mockSettings(ai_enabled: boolean, ai_configured: boolean) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("/api/settings/ai")) {
      const body = JSON.parse(String(init?.body ?? "{}"));
      return new Response(
        JSON.stringify({ ai_enabled: body.enabled, ai_configured }),
        { status: 200 },
      );
    }
    if (url.includes("/api/settings")) {
      return new Response(JSON.stringify({ ai_enabled, ai_configured }), { status: 200 });
    }
    return new Response("{}", { status: 404 });
  });
}

test("reflects the server state on mount", async () => {
  mockSettings(true, true);
  render(<AiToggle />);
  const sw = await screen.findByRole("switch");
  expect(sw).toHaveAttribute("aria-checked", "true");
  expect(sw).not.toBeDisabled();
});

test("PUTs the new value when toggled", async () => {
  const fetchSpy = mockSettings(true, true);
  render(<AiToggle />);
  const sw = await screen.findByRole("switch");
  fireEvent.click(sw);
  await waitFor(() =>
    expect(
      fetchSpy.mock.calls.some(([u]) => String(u).includes("/api/settings/ai")),
    ).toBe(true),
  );
  await waitFor(() => expect(sw).toHaveAttribute("aria-checked", "false"));
});

test("is disabled when AI is not configured", async () => {
  mockSettings(false, false);
  render(<AiToggle />);
  const sw = await screen.findByRole("switch");
  expect(sw).toBeDisabled();
  expect(sw).toHaveAttribute("aria-checked", "false");
});
