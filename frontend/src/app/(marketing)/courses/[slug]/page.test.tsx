import { render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { PublicCourseDetail } from "@/lib/catalogue/courses";

import CoursePage from "./page";

const course: PublicCourseDetail = {
  id: "course-1",
  slug: "spanish",
  title: "Spanish for beginners",
  language: { code: "es", name: "Spanish", native_name: "Español" },
  level: "A1",
  instructor_name: "Samira",
  description: "Learn greetings.\nPractise everyday conversation.",
  skill_areas: ["listening"],
  sections: [{
    id: "section-1", title: "Greetings", position: 1,
    lessons: [{ id: "lesson-1", slug: "hello", title: "Saying hello", position: 1, is_preview: true }],
  }],
  related: [],
};

afterEach(() => vi.unstubAllGlobals());

async function show(value: PublicCourseDetail) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(
    String(url).includes("/me/courses") ? { results: [] } : value,
  ))));
  render(await CoursePage({ params: Promise.resolve({ slug: value.slug }) }));
}

it("preserves published course content and the lesson destination", async () => {
  await show(course);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(course.title);
  expect(screen.getByText((_, element) => element?.tagName === "P" && element.textContent === course.description)).toBeInTheDocument();
  expect(screen.getByText(/Samira/)).toBeInTheDocument();
  expect(screen.getByText("listening")).toBeInTheDocument();
  expect(screen.getByText("1 section", { exact: false })).toHaveTextContent("1 section · 1 lesson");
  expect(screen.getByRole("link", { name: "Saying hello" })).toHaveAttribute("href", "/courses/spanish/lessons/hello");
  expect(screen.getByText("Free preview")).toBeInTheDocument();
});

it("shows an honest empty outline without invented course details", async () => {
  await show({ ...course, description: "", instructor_name: "", skill_areas: [], sections: [] });
  expect(screen.getByText(/0 sections/)).toHaveTextContent("0 sections · 0 lessons");
  expect(screen.getByText(/outline for this course is not published yet/)).toBeVisible();
  expect(screen.queryByText("Free preview")).not.toBeInTheDocument();
  expect(screen.queryByText(/Samira/)).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Related courses" })).not.toBeInTheDocument();
});

it("preserves related courses as a named list with working destinations", async () => {
  await show({ ...course, related: [{ ...course, id: "related-1", slug: "next-spanish", title: "Everyday Spanish" }] });
  const related = screen.getByRole("list", { name: "Related courses" });
  expect(within(related).getByRole("article", { name: "Everyday Spanish" })).toBeVisible();
  expect(within(related).getByRole("link", { name: "Everyday Spanish" })).toHaveAttribute("href", "/courses/next-spanish");
});
