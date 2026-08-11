import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import * as client from "./api/client";

describe("App", () => {
  it("shows API healthy once the health check resolves", async () => {
    vi.spyOn(client, "getHealth").mockResolvedValue({ status: "ok" });
    vi.spyOn(client, "getListings").mockResolvedValue([]);
    render(<App />);
    await waitFor(() => expect(screen.getByText("API healthy")).toBeInTheDocument());
  });

  it("shows API down when the health check fails", async () => {
    vi.spyOn(client, "getHealth").mockRejectedValue(new Error("down"));
    vi.spyOn(client, "getListings").mockResolvedValue([]);
    render(<App />);
    await waitFor(() => expect(screen.getByText("API down")).toBeInTheDocument());
  });
});
