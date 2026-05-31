import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { RunStatusPill } from "./RunStatusPill";
import type { CrawlRun } from "../types";

function run(over: Partial<CrawlRun>): CrawlRun {
  return {
    id: 1,
    source: "kleinanzeigen",
    trigger: "manual",
    status: "done",
    started_at: "2026-05-31T00:00:00Z",
    finished_at: "2026-05-31T00:01:00Z",
    listings_seen: 25,
    listings_new: 5,
    listings_updated: 20,
    listings_gone: 2,
    haiku_calls: 5,
    sonnet_calls: 0,
    opus_calls: 0,
    est_cost_usd: 0.02,
    error: null,
    ...over,
  };
}

test("shows empty state with no run", () => {
  render(<RunStatusPill run={null} />);
  expect(screen.getByText(/No crawls yet/)).toBeInTheDocument();
});

test("shows new/seen and cost for a completed run", () => {
  render(<RunStatusPill run={run({})} />);
  expect(screen.getByText("done")).toBeInTheDocument();
  expect(screen.getByText(/5 new · 25 seen · \$0\.02/)).toBeInTheDocument();
});

test("shows crawling for a running run", () => {
  render(<RunStatusPill run={run({ status: "running" })} />);
  expect(screen.getByText("running")).toBeInTheDocument();
  expect(screen.getByText(/crawling/)).toBeInTheDocument();
});
