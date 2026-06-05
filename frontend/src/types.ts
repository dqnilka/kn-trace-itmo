export type SourceNodeType = 'Chunk' | 'Concept' | 'Assessment' | 'MdChunk'

export type Source = {
  node_id: string
  node_type: SourceNodeType
  score: number
  snippet: string
}

export type ExamGraphHealth = {
  slug: string
  title: string
  nodes: number
  edges: number
  chapters: number
  themes: number
  tasks: number
  concepts: number
  task_concept_links: number
  prereq_edges?: number
}

export type Health = {
  status: 'ok' | 'degraded'
  graph_loaded: boolean
  vector_store_ready: boolean
  llm_configured: boolean
  exams: ExamGraphHealth[]
}


export type Screen =
  | 'onboarding'
  | 'entrance'
  | 'results'
  | 'dashboard'
  | 'practice'
  | 'adaptive'
  | 'learning'
  | 'theory'
  | 'exam'
  | 'wip'

export type UserState = {
  id: number
  name: string
  email: string
  is_admin?: boolean
}

export type AuthUser = {
  id: number
  email: string
  display_name: string | null
  is_admin: boolean
}

export type AuthResponse = {
  token: string
  user: AuthUser
}

export type ServerMastery = {
  exam_slug: string
  themes: Record<string, { asked: number; correct: number }>
}

export type AdminFeedbackSummary = {
  totals: { kind: string; rating: string; n: number }[]
  by_theme: {
    ref: string
    theme_name: string
    likes: number
    dislikes: number
  }[]
  comments: {
    kind: string
    ref: string
    theme_name: string
    comment: string
    created_at: string | null
  }[]
}

export type WipReason = 'theory' | 'other'

export type ThemeMastery = {
  asked: number
  correct: number
  last_practiced: string
}

export type MasteryStore = Record<string, ThemeMastery>

export type ExamVariantSummary = {
  variant_id: number
  taken_at: string
  total: number
  correct: number
  per_chapter: Record<
    string,
    { chapter_id: number; chapter_name: string; asked: number; wrong: number }
  >
}

// API: multi-exam trainer plane

export type ExamListItem = {
  slug: string
  title: string
  subtitle: string
  version: string
  published: boolean
  stats: { chapters: number; themes: number; tasks: number; options: number }
}

export type ExamListResponse = { exams: ExamListItem[] }

export type ExplainResponse = {
  task_id: number
  theme_code: string
  chapter_name: string | null
  theme_name: string | null
  correct_label: string
  picked_label: string | null
  is_correct: boolean
  explanation_md: string
  sources: Source[]
  generation_mode: 'llm' | 'extractive'
}

export type ConceptUpdate = {
  concept_id: string
  concept_term: string
  p_before: number
  p_after: number
  weight: number
}

export type EventResponse = {
  user_id: number
  task_id: number
  is_correct: boolean
  updates: ConceptUpdate[]
  overall_mastery: number | null
}

export type RecommendItem = {
  task_id: number
  score: number
  expected_p_correct: number
  reason: string
  target_concepts: [string, string, number][]
  due_score?: number
}

export type RecommendResponse = {
  user_id: number
  target_p: number
  items: RecommendItem[]
}

export type DueConcept = {
  concept_id: string
  term: string
  p_l: number
  retrievability: number
  last_seen_iso: string | null
}

export type ThemeArticleSection = {
  chunk_id: string
  section_path: string
  snippet: string
  score: number
  char_offset: number
  char_length: number
  excerpt: string
}

export type ThemeConcept = {
  id: string
  term: string
  definition: string
  prereq_count: number
}

export type ThemeArticleResponse = {
  slug: string
  theme_code: string
  theme_name: string
  chapter_name: string | null
  chapter_num: number | null
  sections: ThemeArticleSection[]
  summary_md: string | null
  summary_cached: boolean
  concepts: ThemeConcept[]
  task_count: number
}

export type MasteryResponse = {
  user_id: number
  exam_slug: string
  events: number
  overall: number | null
  by_concept: Record<string, number>
  by_theme: Record<string, number>
  by_chapter: Record<string, number>
  due_concepts?: DueConcept[]
}

// === Admin types ===

export type AdminExam = {
  slug: string
  title: string
  subtitle: string
  version: string
  published: boolean
  has_bank: boolean
  has_theory: boolean
  root: string
  manifest: Record<string, unknown>
}

export type AdminExamsResponse = { exams: AdminExam[] }

export type AdminRun = {
  run_id: string
  exam_slug: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
  started_at: string
  finished_at: string | null
  exit_code: number | null
  cmd: string[]
  log_path: string
  notes: string
}

export type AdminRunsResponse = { runs: AdminRun[] }

export type AdminIngestOptions = {
  top_k?: number
  min_score?: number
  limit?: number
  llm_rerank?: boolean
  llm_top_k?: number
  llm_batch?: number
}

export type BankChapter = {
  id: number
  num: number
  name: string
}

export type BankTheme = {
  id: number
  chapter_id: number
  code: string
  name: string
}

export type BankOption = {
  label: string
  text: string
  is_correct: boolean
}

export type BankTask = {
  id: number
  theme_code: string
  task_number: string
  task_text: string
  answer_type: 'single_choice'
  difficulty: number | null
  solution_text: string
  options: BankOption[]
}

export type ExamBank = {
  _meta: {
    exam: string
    source_file: string
    generated_at: string
    stats: { chapters: number; themes: number; tasks: number; options: number }
  }
  chapters: BankChapter[]
  themes: BankTheme[]
  tasks: BankTask[]
}

export type BankAnswer = {
  task_id: number
  chapter_id: number
  chapter_name: string
  theme_code: string
  theme_name: string
  picked_label: string | null
  correct_label: string
  is_correct: boolean
}

export type BankEntranceResult = {
  user_id: number
  total: number
  correct: number
  incorrect: number
  per_chapter: Record<
    string,
    { chapter_id: number; chapter_name: string; asked: number; wrong: number }
  >
  answers: BankAnswer[]
  taken_at: string
}
