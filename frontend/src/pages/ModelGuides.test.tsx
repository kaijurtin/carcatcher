import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

// Mock the API client so the page doesn't hit the network.
vi.mock("../api/client", () => ({
  getModelGuides: vi.fn(),
  getModelGuide: vi.fn(),
  createModelGuide: vi.fn(),
}));
// Mock react-markdown (ESM) to a trivial passthrough — we only assert content flows in.
vi.mock("react-markdown", () => ({
  default: ({ children }: { children: string }) => <div>{children}</div>,
}));
vi.mock("remark-gfm", () => ({ default: () => {} }));

import { createModelGuide, getModelGuide, getModelGuides } from "../api/client";
import { ModelGuides } from "./ModelGuides";

afterEach(() => vi.restoreAllMocks());

test("lists guides and renders the selected guide's markdown", async () => {
  vi.mocked(getModelGuides).mockResolvedValue([
    { make: "Volkswagen", model: "ID.4", title: "Volkswagen ID.4", updated: "2026-06-01" },
  ]);
  vi.mocked(getModelGuide).mockResolvedValue({
    make: "Volkswagen",
    model: "ID.4",
    front_matter: { make: "Volkswagen", model: "ID.4" },
    markdown: "# Volkswagen ID.4 — buyer's guide\n\nKnown problems here.",
  });

  render(<ModelGuides />);

  // Sidebar entry (auto-selected first guide).
  expect(await screen.findByRole("button", { name: /Volkswagen ID\.4/ })).toBeInTheDocument();
  // Guide body rendered.
  await waitFor(() =>
    expect(screen.getByText(/Known problems here/)).toBeInTheDocument(),
  );
  expect(getModelGuide).toHaveBeenCalledWith("Volkswagen", "ID.4");
});

test("shows empty state when there are no guides", async () => {
  vi.mocked(getModelGuides).mockResolvedValue([]);
  render(<ModelGuides />);
  expect(await screen.findByText(/No model guides yet/)).toBeInTheDocument();
});

test("create button submits make/model and shows a generating row", async () => {
  vi.mocked(getModelGuides).mockResolvedValue([]);
  vi.mocked(createModelGuide).mockResolvedValue(undefined);

  render(<ModelGuides />);
  await waitFor(() => expect(getModelGuides).toHaveBeenCalled());

  fireEvent.change(screen.getByLabelText("Make"), { target: { value: "Tesla" } });
  fireEvent.change(screen.getByLabelText("Model"), { target: { value: "Model 3" } });
  fireEvent.click(screen.getByRole("button", { name: /\+ Create guide/ }));

  await waitFor(() =>
    expect(createModelGuide).toHaveBeenCalledWith("Tesla", "Model 3"),
  );
  expect(await screen.findByText(/Generating Tesla Model 3/)).toBeInTheDocument();
});

test("filter box narrows the guide list", async () => {
  vi.mocked(getModelGuides).mockResolvedValue([
    { make: "Volkswagen", model: "ID.4", title: "Volkswagen ID.4", updated: null, status: "ready" },
    { make: "Tesla", model: "Model 3", title: "Tesla Model 3", updated: null, status: "ready" },
  ]);
  vi.mocked(getModelGuide).mockResolvedValue({
    make: "Volkswagen",
    model: "ID.4",
    front_matter: {},
    markdown: "guide",
  });

  render(<ModelGuides />);
  expect(await screen.findByRole("button", { name: /Tesla Model 3/ })).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Filter guides"), { target: { value: "tesla" } });

  expect(screen.queryByRole("button", { name: /Volkswagen ID\.4/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Tesla Model 3/ })).toBeInTheDocument();
});
