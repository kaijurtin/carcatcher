import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { SearchBar } from "./SearchBar";

test("submits the typed query", () => {
  const onSearch = vi.fn();
  render(<SearchBar onSearch={onSearch} onClear={() => {}} loading={false} active={false} />);
  fireEvent.change(screen.getByPlaceholderText(/plain language/), {
    target: { value: "cheap golf" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Search/ }));
  expect(onSearch).toHaveBeenCalledWith("cheap golf");
});

test("does not submit an empty query", () => {
  const onSearch = vi.fn();
  render(<SearchBar onSearch={onSearch} onClear={() => {}} loading={false} active={false} />);
  fireEvent.click(screen.getByRole("button", { name: /Search/ }));
  expect(onSearch).not.toHaveBeenCalled();
});

test("shows clear button only when active and calls onClear", () => {
  const onClear = vi.fn();
  const { rerender } = render(
    <SearchBar onSearch={() => {}} onClear={onClear} loading={false} active={false} />,
  );
  expect(screen.queryByRole("button", { name: /Clear/ })).not.toBeInTheDocument();
  rerender(<SearchBar onSearch={() => {}} onClear={onClear} loading={false} active={true} />);
  fireEvent.click(screen.getByRole("button", { name: /Clear/ }));
  expect(onClear).toHaveBeenCalled();
});
