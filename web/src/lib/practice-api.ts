/**
 * Typed client for the Plus FastAPI backend's public /api/questions endpoint
 * and the student-scoped /api/sessions routes.
 *
 * NOTE: /api/sessions/* routes are locked by default
 * (PLUS_REAL_STUDENT_DATA=1 requires a server-verified X-Student-Id header).
 * They return HTTP 503 unless the backend is configured for real student data.
 * The frontend never fabricates a student_id or bypasses this boundary.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_PLUS_API_BASE_URL ?? "http://127.0.0.1:8000";

export type ApprovedQuestion = {
  id: string;
  subject: string;
  topic: string;
  question_type: string;
  question_text: string;
  options: { letter: string; text: string }[];
  context: string | null;
};

export type CreateSessionResult = {
  session_id: string;
  state: string;
  session_type: string;
  total: number;
};

export type SubmitAnswerResult = {
  is_correct: boolean;
  correct_answer?: string | null;
  explanation?: string | null;
};

async function backend<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = new URL(path.replace(/^\/+/, ""), API_BASE).toString();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    throw new Error("We couldn't reach the practice service. Please try again.");
  }
  const payload = await response.json().catch(() => null) as {
    detail?: unknown;
    error?: unknown;
  } | null;
  if (!response.ok) {
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : typeof payload?.error === "string"
          ? payload.error
          : "";
    throw new Error(
      response.status >= 500
        ? "We couldn't reach the practice service. Please try again."
        : detail || "We couldn't complete that just now. Please try again."
    );
  }
  if (payload === null) {
    throw new Error("The practice service returned an invalid response.");
  }
  return payload as T;
}

export async function fetchApprovedQuestions(): Promise<ApprovedQuestion[]> {
  return backend<ApprovedQuestion[]>("/api/questions");
}

export async function createPracticeSession(studentId: string): Promise<CreateSessionResult> {
  return backend<CreateSessionResult>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ student_id: studentId, session_type: "practice" }),
  });
}

export async function submitPracticeAnswer(
  sessionId: string,
  questionId: string,
  chosenAnswer: string,
): Promise<SubmitAnswerResult> {
  return backend<SubmitAnswerResult>(`/api/sessions/${encodeURIComponent(sessionId)}/answer`, {
    method: "POST",
    body: JSON.stringify({ question_id: questionId, chosen_answer: chosenAnswer }),
  });
}