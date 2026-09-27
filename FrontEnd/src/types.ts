export type Language = "fr" | "ary";
export type Tab = "explain" | "treatment" | "chat" | "accuracy";
export type Translate = (fr: string, ary: string) => string;
export interface Medicine {
  name: string;
  instructions: string;
  dose?: string;
  times?: string[];
  duration_days?: number;
}
export interface Explanation {
  summary: string;
  document_type: string;
  items: { title: string; detail: string }[];
  next_steps: string[];
  uncertainties: string[];
  emergency: { detected: boolean; message: string };
  medicines: Medicine[];
}
export interface Message {
  role: "user" | "assistant";
  content: string;
  emergency?: boolean;
}
export interface Treatment {
  id: string;
  name: string;
  dose: string;
  instructions: string;
  times: string[];
  start: string;
  days: number;
}
export interface Plan {
  treatments: Treatment[];
  taken: string[];
  demo: boolean;
}
export interface AccuracyReport {
  total: number;
  passed: number;
  generated_at: string;
  cases: {
    question: string;
    expected: string;
    actual: string;
    passed: boolean;
    category: string;
  }[];
}
