import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { RefreshControls } from "./RefreshControls";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.removeItem("carcatcher_cron_secret");
});

function mockFetch(refreshStatus = 202) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("/api/runs")) {
      return new Response(JSON.stringify([]), { status: 200 });
    }
    if (url.includes("/api/refresh")) {
      expect((init?.headers as Record<string, string>)["X-Cron-Secret"]).toBe("s3cr3t");
      return new Response(JSON.stringify({ status: "scheduled" }), {
        status: refreshStatus,
      });
    }
    return new Response("{}", { status: 404 });
  });
}

test("renders the refresh button and empty run state", async () => {
  mockFetch();
  render(<RefreshControls />);
  expect(screen.getByRole("button", { name: /Refresh/ })).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByText(/No crawls yet/)).toBeInTheDocument(),
  );
});

test("prompts for a secret when none stored, then triggers refresh", async () => {
  const fetchSpy = mockFetch(202);
  vi.spyOn(window, "prompt").mockReturnValue("s3cr3t");

  render(<RefreshControls />);
  fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));

  await waitFor(() =>
    expect(localStorage.getItem("carcatcher_cron_secret")).toBe("s3cr3t"),
  );
  await waitFor(() =>
    expect(
      fetchSpy.mock.calls.some(([u]) => String(u).includes("/api/refresh")),
    ).toBe(true),
  );
});

test("does nothing when the secret prompt is cancelled", async () => {
  const fetchSpy = mockFetch();
  vi.spyOn(window, "prompt").mockReturnValue(null);

  render(<RefreshControls />);
  fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));

  // No refresh call should be made.
  await waitFor(() =>
    expect(
      fetchSpy.mock.calls.some(([u]) => String(u).includes("/api/refresh")),
    ).toBe(false),
  );
});
