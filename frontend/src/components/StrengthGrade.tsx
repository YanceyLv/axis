interface StrengthGradeProps {
  grade: string;
  score: number;
}

export function StrengthGrade({ grade, score }: StrengthGradeProps) {
  const clampedScore = Math.max(0, Math.min(100, score));

  return (
    <div className="strength">
      <strong>{grade}</strong>
      <div
        className="strength-track"
        role="progressbar"
        aria-label={`强度 ${clampedScore}%`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={clampedScore}
      >
        <span style={{ width: `${clampedScore}%` }} />
      </div>
    </div>
  );
}
