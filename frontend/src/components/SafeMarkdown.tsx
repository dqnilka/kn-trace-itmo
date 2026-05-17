import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'

/**
 * Единая обёртка над ReactMarkdown с включённой санитизацией.
 *
 * Зачем sanitize, если ReactMarkdown по умолчанию НЕ рендерит сырой HTML?
 * Defense in depth. Если кто-то добавит `rehype-raw` в этот компонент в
 * будущем (стандартный путь при попытке поддержать inline HTML), без
 * `rehype-sanitize` любой LLM-вывод или backend-payload с `<script>` сразу
 * превращается в XSS. С sanitize — нет.
 *
 * Дополнительно: позволяет передавать `components` для кастомного рендера
 * элементов (см. TheoryScreen — там перехватывается <strong> для термов).
 */
export default function SafeMarkdown({
  children,
  components,
}: {
  children: string
  components?: Components
}) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeSanitize]}
      components={components}
    >
      {children}
    </ReactMarkdown>
  )
}
