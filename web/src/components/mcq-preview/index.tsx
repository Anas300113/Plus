"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { LoaderCircle } from "lucide-react";
import { QuestionCard } from "./question-card";
import type { ApprovedQuestion } from "@/lib/practice-api";
import { fetchApprovedQuestions } from "@/lib/practice-api";

type PreviewStatus = "loading" | "empty" | "error" | "ready";

export function McqPreview() {
  const [status, setStatus] = useState<PreviewStatus>("loading");
  const [question, setQuestion] = useState<ApprovedQuestion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [checkStatus, setCheckStatus] = useState<"idle" | "checking" | "feedback">("idle");
  const [correctAnswer, setCorrectAnswer] = useState<string | null | undefined>(null);
  const [explanation, setExplanation] = useState<string | null | undefined>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadQuestion = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const questions = await fetchApprovedQuestions();
      if (!questions || questions.length === 0) {
        setStatus("empty");
        return;
      }
      // Pick the first approved question; mark server-side only.
      setQuestion(questions[0]);
      setStatus("ready");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "We couldn't load a practice question right now.",
      );
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    loadQuestion();
  }, [loadQuestion]);

  const handleSelect = (letter: string) => {
    setSelectedAnswer(letter);
    setCheckStatus("idle");
    setCorrectAnswer(undefined);
    setExplanation(undefined);
  };

  const handleCheck = async () => {
    if (!selectedAnswer || !question) return;
    setCheckStatus("checking");
    setIsSubmitting(true);
    try {
      // Server-side marking: the correct answer is never sent to the browser.
      // We submit the chosen answer and the server tells us if it's correct.
      const result = await fetch(
        `${process.env.NEXT_PUBLIC_PLUS_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/sessions/demo/answer`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ question_id: question.id, chosen_answer: selectedAnswer }),
        },
      );
      if (!result.ok) {
        // Sessions are locked without server-verified identity. Treat as a
        // demo preview limitation, not a fake result.
        setCheckStatus("feedback");
        setCorrectAnswer(null);
        setExplanation(
          "Practice sessions require a signed-in account. Create an account to save your progress.",
        );
        return;
      }
      const data = await result.json();
      setCheckStatus("feedback");
      setCorrectAnswer(data.correct_answer ?? null);
      setExplanation(data.explanation ?? null);
    } catch {
      setCheckStatus("feedback");
      setCorrectAnswer(null);
      setExplanation("We couldn't check that answer right now. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRetry = () => {
    setSelectedAnswer(null);
    setCheckStatus("idle");
    setCorrectAnswer(undefined);
    setExplanation(undefined);
  };

  const handleReload = () => {
    loadQuestion();
  };

  return (
    <section className="mcq-preview-section">
      <span className="signup-preview-label">TRY A QUESTION</span>
      <AnimatePresence mode="wait">
        {status === "loading" && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mcq-empty"
          >
            <LoaderCircle className="mcq-spinner" size={20} aria-hidden="true" />
            <span>Getting a question ready…</span>
          </motion.div>
        )}
        {status === "empty" && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mcq-empty"
          >
            <p>No approved practice questions are available right now.</p>
            <button className="secondary-button" onClick={handleReload} style={{ marginTop: 12 }}>
              Try again
            </button>
          </motion.div>
        )}
        {status === "error" && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mcq-empty"
          >
            <p className="mcq-error">{error}</p>
            <button className="secondary-button" onClick={handleReload} style={{ marginTop: 12 }}>
              Try again
            </button>
          </motion.div>
        )}
        {status === "ready" && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            className=""
          >
            <QuestionCard
              question={question}
              status={checkStatus}
              selectedAnswer={selectedAnswer}
              correctAnswer={correctAnswer}
              explanation={explanation}
              onSelect={handleSelect}
              onCheck={handleCheck}
              onRetry={handleRetry}
              isSubmitting={isSubmitting}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}