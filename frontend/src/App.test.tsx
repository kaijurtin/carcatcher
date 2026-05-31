import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";

afterEach(() => vi.restoreAllMocks());

test("renders the CarCatcher header", () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
  );
  render(<App />);
  expect(screen.getByText(/CarCatcher/)).toBeInTheDocument();
});

test("shows API healthy when health endpoint returns ok", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
  );
  render(<App />);
  await waitFor(() => expect(screen.getByText("API healthy")).toBeInTheDocument());
});

test("shows API down when health check fails", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));
  render(<App />);
  await waitFor(() => expect(screen.getByText("API down")).toBeInTheDocument());
});
