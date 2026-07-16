interface Props extends React.ButtonHTMLAttributes<HTMLButtonElement> { variant?: "primary"|"secondary"|"ghost"; size?: "sm"|"md" }
export default function Button({ variant="primary", size="md", style, children, ...props }: Props) {
  const base: React.CSSProperties = { display:"inline-flex", alignItems:"center", justifyContent:"center", gap:9, borderRadius:"var(--radius)", fontWeight:600, transition:"all 0.2s", cursor:props.disabled?"not-allowed":"pointer", opacity:props.disabled?0.5:1, fontSize:size==="sm"?19:20, padding:size==="sm"?"10px 19px":"16px 29px" };
  const v: Record<string, React.CSSProperties> = { primary:{background:"var(--primary-solid)",color:"#fff",boxShadow:"0 0 15px var(--primary-glow)"}, secondary:{background:"var(--surface)",color:"var(--text-primary)",border:"1px solid var(--border-glass)"}, ghost:{background:"transparent",color:"var(--text-muted)"} };
  return <button style={{...base,...v[variant],...style}} {...props}>{children}</button>;
}
