import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CoursesShelf from "@/components/courses/CoursesShelf";
import { initI18n } from "@/i18n/init";
import { listCourses, type StudyCourse } from "@/lib/courses-api";
import { listAllSessions } from "@/lib/session-api";
import { ApiError } from "@/shared/api/errors";

initI18n("en");

vi.mock("@/lib/courses-api", () => ({
  DEFAULT_COURSE_COLORS: ["#C65D2E"],
  listCourses: vi.fn(),
  createCourse: vi.fn(),
}));

vi.mock("@/lib/session-api", () => ({
  listAllSessions: vi.fn(),
}));

const mockedListCourses = vi.mocked(listCourses);
const mockedListAllSessions = vi.mocked(listAllSessions);

function course(overrides: Partial<StudyCourse> = {}): StudyCourse {
  return {
    id: "course-1",
    name: "Operating Systems",
    description: "",
    color: "#C65D2E",
    created_at: 0,
    updated_at: 0,
    instructions: "",
    agent_notes: "",
    default_capability: "chat",
    default_persona: "",
    resources: [],
    syllabus: [],
    status: "active",
    archived_at: 0,
    ...overrides,
  };
}

function apiError(
  status: number,
  message: string,
  correlationId?: string,
): ApiError {
  return new ApiError({
    code: `http_${status}`,
    message,
    retryable: status >= 500,
    scope: "network",
    status,
    correlationId,
  });
}

beforeEach(() => {
  mockedListCourses.mockReset();
  mockedListAllSessions.mockReset();
  mockedListAllSessions.mockResolvedValue([]);
});

describe("courses shelf", () => {
  it("shows a permission refusal instead of an empty shelf on 403", async () => {
    mockedListCourses.mockRejectedValue(
      apiError(
        403,
        "This learning account cannot use the reading surface.",
        "req-forbidden",
      ),
    );

    render(<CoursesShelf />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("You do not have access to courses");
    expect(alert).toHaveTextContent(
      "This learning account cannot use the reading surface.",
    );
    expect(alert).toHaveTextContent("req-forbidden");
    expect(alert).toHaveTextContent("Sign in");
    expect(
      screen.queryByRole("button", { name: /Create your first course/ }),
    ).not.toBeInTheDocument();
  });

  it("offers a retry, with the server's diagnostic id, when the server fails", async () => {
    const user = userEvent.setup();
    mockedListCourses
      .mockRejectedValueOnce(
        apiError(500, "Request failed (500)", "req-unavailable"),
      )
      .mockResolvedValueOnce([course()]);

    render(<CoursesShelf />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Courses could not load");
    expect(alert).toHaveTextContent("req-unavailable");
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Operating Systems")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
    );
  });

  it("still shows the empty shelf when the account simply has no courses", async () => {
    mockedListCourses.mockResolvedValue([]);

    render(<CoursesShelf />);

    // The cell's accessible name carries its whole explanatory copy, so match
    // on the leading label rather than the exact string.
    expect(
      await screen.findByRole("button", { name: /Create your first course/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("lets a learner copy the diagnostic id to quote in a report", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    mockedListCourses.mockRejectedValue(
      apiError(500, "Request failed (500)", "req-copy"),
    );

    render(<CoursesShelf />);

    await user.click(
      await screen.findByRole("button", { name: "Copy diagnostic ID" }),
    );

    expect(writeText).toHaveBeenCalledWith("req-copy");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Copied" }),
      ).toBeInTheDocument(),
    );
  });
});
