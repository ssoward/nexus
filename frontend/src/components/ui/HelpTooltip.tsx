interface Props {
  text: string
  side?: 'above' | 'below'
  width?: string
}

export function HelpTooltip({ text, side = 'below', width = 'w-56' }: Props) {
  const position = side === 'above'
    ? 'bottom-full mb-1.5'
    : 'top-full mt-1.5'

  return (
    <span className="relative group inline-flex items-center">
      <span className="text-terminal-fg/30 hover:text-terminal-fg/60 cursor-help text-xs select-none">ⓘ</span>
      <span className={`absolute ${position} left-1/2 -translate-x-1/2 ${width} px-2 py-1.5 text-[0.625rem] font-mono leading-relaxed bg-[#1c2128] border border-terminal-border rounded shadow-lg text-terminal-fg/80 invisible opacity-0 group-hover:visible group-hover:opacity-100 transition-opacity z-50 pointer-events-none whitespace-normal`}>
        {text}
      </span>
    </span>
  )
}
