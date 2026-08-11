import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RefreshControls } from "./RefreshControls";
import * as client from "../api/client";

describe("RefreshControls", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows a loading state while refreshing, then the summary", async () => {
    vi.spyOn(client, "refresh").mockResolvedValue({
      added: 2,
      updated: 1,
      gone: 0,
      failed_sources: [],
      refreshed_at: "2026-08-11T12:00:00Z",
    });
    const onComplete = vi.fn();
    render(<RefreshControls onComplete={onComplete} />);

    fireEvent.click(screen.getByRole("button", { name: "Update search" }));
    expect(screen.getByRole("button")).toHaveTextContent("Updating…");

    await waitFor(() => expect(onComplete).toHaveBeenCalled());
    expect(screen.getByText(/2 new/)).toBeInTheDocument();
  });

  it("shows an error message when refresh fails", async () => {
    vi.spyOn(client, "refresh").mockRejectedValue(new Error("network down"));
    render(<RefreshControls />);
    fireEvent.click(screen.getByRole("button", { name: "Update search" }));
    await waitFor(() => expect(screen.getByText("network down")).toBeInTheDocument());
  });

  it("shows which sources failed when a refresh partially fails", async () => {
    vi.spyOn(client, "refresh").mockResolvedValue({
      added: 1,
      updated: 0,
      gone: 0,
      failed_sources: ["vw"],
      refreshed_at: "2026-08-11T12:00:00Z",
    });
    render(<RefreshControls />);
    fireEvent.click(screen.getByRole("button", { name: "Update search" }));
    await waitFor(() => expect(screen.getByText(/vw/)).toBeInTheDocument());
  });
});
