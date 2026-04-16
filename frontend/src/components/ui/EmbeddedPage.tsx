interface Props {
  url: string
  name: string
}

export function EmbeddedPage({ url, name }: Props) {
  return (
    <div className="flex flex-col h-full border-l border-terminal-border">
      <div className="shrink-0 flex items-center px-2 py-1 bg-[#161b22] border-b border-terminal-border">
        <span className="text-xs font-mono text-terminal-fg truncate">{name}</span>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto text-[10px] text-terminal-active hover:underline shrink-0"
        >
          Open in new tab
        </a>
      </div>
      <iframe
        src={url}
        sandbox="allow-scripts allow-forms allow-popups allow-same-origin"
        className="flex-1 w-full border-0 bg-white"
        title={name}
      />
    </div>
  )
}
