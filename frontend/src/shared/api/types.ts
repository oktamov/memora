/** Response shapes mirroring the backend's Pydantic schemas. */

export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
};

export type User = {
  id: string;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  native_lang: string;
  ui_lang: string;
  daily_new_limit: number;
  daily_review_limit: number;
  lookup_quota_per_day: number;
  timezone: string;
  reminder_hour: number | null;
  reminder_enabled: boolean;
  is_active: boolean;
  created_at: string;
};

export type DeckKind = 'normal' | 'daily';

export type Deck = {
  id: string;
  name: string;
  source_lang: string;
  target_lang: string;
  kind: DeckKind;
  daily_date: string | null;
  archived_at: string | null;
  created_at: string;
  card_count: number;
  due_count: number;
  new_count: number;
};

export type Meaning = {
  pos: string | null;
  definition: string;
  gloss_en: string | null;
  examples: string[];
};

export type LookupResult = {
  term: string;
  source_lang: string;
  target_lang: string;
  ipa: string | null;
  meanings: Meaning[];
  provider: string;
  cache: 'miss' | 'redis' | 'db';
  quota_used: number;
  quota_limit: number;
};

export type CardMeaning = {
  pos: string | null;
  definition: string;
  gloss_en: string | null;
};

export type ExampleSource = 'user' | 'provider';

export type CardExample = {
  text: string;
  translation: string | null;
  source: ExampleSource;
};

export type CardState = {
  due: string;
  state: number;
  reps: number;
  lapses: number;
  suspended: boolean;
  stability: number | null;
  difficulty: number | null;
  last_review: string | null;
};

export type Card = {
  id: string;
  deck_id: string;
  term: string;
  display_term: string;
  ipa: string | null;
  pos: string | null;
  meanings: CardMeaning[];
  examples: CardExample[];
  note: string | null;
  source_lang: string;
  target_lang: string;
  created_at: string;
  state: CardState | null;
};

export type Page<T> = {
  items: T[];
  next_cursor: string | null;
};

export type ReviewCounts = {
  new: number;
  learning: number;
  due: number;
  total: number;
};

export type QueueItem = {
  card: Card;
  state: CardState;
};

export type ReviewQueue = {
  items: QueueItem[];
  new_remaining: number;
  counts: ReviewCounts;
};

export type AnswerResult = {
  card_id: string;
  due: string;
  state: number;
  scheduled_days: number;
};

/** 1 again, 2 hard, 3 good, 4 easy. */
export type Rating = 1 | 2 | 3 | 4;

export type DeckReviewCounts = ReviewCounts & { deck_id: string };

export type ReviewCountsOverview = {
  total: ReviewCounts;
  decks: DeckReviewCounts[];
};

export type DailyActivity = {
  date: string;
  reviews: number;
};

export type StatsOverview = {
  streak_days: number;
  longest_streak_days: number;
  total_cards: number;
  cards_due_today: number;
  reviews_today: number;
  retention_rate: number | null;
  reviews_per_day: DailyActivity[];
};
