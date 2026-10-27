"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Lightbulb, LoaderCircle, X } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import type { ApprovedQuestion } from "@/lib/practice-api";

type QuestionCardProps = {
  question: ApprovedQuestion | null;
  status: "idle" | "checking" | "feedback";
  selectedAnswer: string | null;
  correctAnswer: string | null | undefined;
  explanation: string | null | undefined;
  onSelect: (letter: string) => void;
  onCheck: () => void;
  onRetry: () => void;
  isSubmitting: boolean;
};

export function QuestionCard({
  question,
  status,
  selectedAnswer,
  correctAnswer,
  explanation,
  onSelect,
  onCheck,
  onRetry,
  isSubmitting,
}: QuestionCardProps) {
  const feedbackRef = useRef<HTMLDivElement>(null);

  const letterFor = (answer: string | null | undefined) =>
    question?.options.find((o) => o.text === answer)?.letter;

  if (!question) {
    return (
      <div className="mcq-empty">
        <p>No approved practice questions are available right now.</p>
      </div>
    );
  }

  const isCorrect = selectedAnswer
    ? selectedAnswer === letterFor(correctAnswer)
    : null;

  return (
    <div className="mcq-preview-card">
      <span className="mcq-subject">{question.subject} / {question.topic}</span>
      <p className="mcq-prompt">{question.question_text}</p>
      {question.context && (
        <p className="mcq-support">{question.context}</p>
      )}
      <div className="mcq-answer-list">
        {question.options.map(({ letter, text }) => {
          const isSelected = selectedAnswer === letter;
          const isCorrectOption = letter === letterFor(correctAnswer);
          return (
            <label
              key={letter}
              className={`mcq-option ${
                isSelected ? "is-selected" : ""
              } ${isCorrectOption && status === "feedback" ? "is-correct" : ""} ${
                isSelected && status === "feedback" && !isCorrectOption
                  ? "is-wrong"
                  : ""
              }`}
            >
              <input
                type="radio"
                name="mcq-answer"
                value={letter}
                checked={isSelected}
                onChange={() => onSelect(letter)}
                aria-label={`${letter}: ${text}`}
              />
              <span className="mcq-letter" aria-hidden="true">{letter}</span>
              <span className="mcq-text">{text}</span>
              {isSelected && status === "feedback" && (
                <span className="mcq-selected-check" aria-hidden="true">
                  {isCorrectOption ? <Check size={17} strokeWidth={2.5} /> : <X size={17} strokeWidth={2.5} />}
                </span>
              )}
            </label>
          );
        })}
      </div>

      {status === "feedback" && isCorrect === false && (
        <p className="mcq-error" role="alert">
          Not quite yet. Have another look at the question and try again.
        </p>
      )}

      <div className="mcq-footer">
        {status === "idle" && selectedAnswer ? (
          <button
            className="mcq-check-button"
            onClick={onCheck}
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <>
                <LoaderCircle className="mcq-spinner" size={16} aria-hidden="true" />
                Checking…
              </>
            ) : (
              <>
                Check answer <span className="sr-only">for this question</span>
              </>
            )}
          </button>
        ) : null}

        {status === "feedback" && isCorrect && (
          <div className="mcq-feedback mcq-feedback-correct" role="status" aria-live="polite">
            <span className="mcq-feedback-icon" aria-hidden="true">
              <Check size={18} strokeWidth={2.5} />
            </span>
            <div className="mcq-feedback-copy">
              <strong>That's right.</strong>
              <p>{explanation ?? "That is the correct answer."}</p>
            </div>
            <button className="cta-button" onClick={onRetry}>
              Try another question <span aria-hidden="true">→</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}