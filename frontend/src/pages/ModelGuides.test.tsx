import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

// Mock the API client so the page doesn't hit the network.
vi.mock("../api/client", () => ({
  getModelGuides: vi.fn(),
  getModelGuide: vi.fn(),
}));
// Mock react-markdown (ESM) to a trivial passthrough — we only assert content flows in.
vi.mock("react-markdown", () => ({
  default: ({ children }: { children: string }) => <div>{children}</div>,
}));
vi.mock("remark-gfm", () => ({ default: () => {} }));

import { getModelGuide, getModelGuides } from "../api/client";
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
